# server.py - Main server script
import socket
import json
import threading
import time
import importlib.util
import sys
import os
from pathlib import Path


class TestServer:
    def __init__(self, host='localhost', port=5001):
        self.host = host
        self.port = port
        self.server_socket = None
        self.running = False
        self.clients = {}
        self.current_test = None
        self.test_running = False
        self.current_model_instance = None  # Track current model instance

    def start_server(self):
        """Start the server and listen for connections"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.running = True

            print(f"Server started on {self.host}:{self.port}")
            print("Waiting for client connections...")

            while self.running:
                try:
                    client_socket, client_address = self.server_socket.accept()
                    print(f"Client connected from {client_address}")

                    client_id = f"{client_address[0]}:{client_address[1]}"
                    self.clients[client_id] = {
                        'socket': client_socket,
                        'address': client_address,
                        'thread': None
                    }

                    # Start a thread to handle this client
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, client_id),
                        daemon=True
                    )
                    client_thread.start()
                    self.clients[client_id]['thread'] = client_thread

                except socket.error as e:
                    if self.running:
                        print(f"Error accepting connection: {e}")

        except Exception as e:
            print(f"Server startup error: {e}")
        finally:
            self.cleanup()

    def handle_client(self, client_socket, client_id):
        """Handle messages from a specific client"""
        try:
            # Send initial status
            self.send_to_client(client_socket, {
                "message": f"Connected to server. Status: {'Running' if self.test_running else 'Idle'}",
                "status": "running" if self.test_running else "idle"
            })

            while self.running:
                try:
                    data = client_socket.recv(4096)
                    if not data:
                        break

                    # Parse JSON message
                    try:
                        message = json.loads(data.decode('utf-8').strip())
                        print(f"Received from {client_id}: {message}")
                        self.process_client_message(client_socket, client_id, message)
                    except json.JSONDecodeError as e:
                        print(f"JSON decode error from {client_id}: {e}")
                        self.send_to_client(client_socket, {
                            "message": f"Invalid JSON format: {e}",
                            "status": "error"
                        })

                except socket.timeout:
                    continue
                except socket.error as e:
                    print(f"Client {client_id} disconnected: {e}")
                    break

        except Exception as e:
            print(f"Error handling client {client_id}: {e}")
        finally:
            self.disconnect_client(client_id)

    def process_client_message(self, client_socket, client_id, message):
        """Process commands from client"""
        command = message.get('command', '').lower()

        if command == 'start':
            self.handle_start_command(client_socket, client_id, message)
        elif command == 'stop':
            self.handle_stop_command(client_socket, client_id)
        elif command == 'status':
            self.handle_status_command(client_socket, client_id)
        else:
            self.send_to_client(client_socket, {
                "message": f"Unknown command: {command}",
                "status": "error"
            })

    def handle_start_command(self, client_socket, client_id, message):
        """Handle start test command"""
        if self.test_running:
            self.send_to_client(client_socket, {
                "message": "Test already running. Please stop current test first.",
                "status": "running"
            })
            return

        test_config = message.get('test_config', {})
        if not test_config:
            self.send_to_client(client_socket, {
                "message": "No test configuration provided",
                "status": "error"
            })
            return

        # Validate required fields
        required_fields = ['serial_number', 'models', 'stages', 'temperatures', 'bands', 'test_cases']
        missing_fields = [field for field in required_fields if not test_config.get(field)]

        if missing_fields:
            self.send_to_client(client_socket, {
                "message": f"Missing required fields: {', '.join(missing_fields)}",
                "status": "error"
            })
            return

        # Start the test
        self.start_test(client_socket, client_id, test_config)

    def handle_stop_command(self, client_socket, client_id):
        """Handle stop test command"""
        if not self.test_running:
            self.send_to_client(client_socket, {
                "message": "No test currently running",
                "status": "idle"
            })
            return

        self.stop_test(client_socket, client_id)

    def handle_status_command(self, client_socket, client_id):
        """Handle status request"""
        status = "running" if self.test_running else "idle"
        message = f"Server status: {status.title()}"

        if self.current_test:
            message += f" | Current test: {self.current_test.get('serial_number', 'Unknown')}"

        self.send_to_client(client_socket, {
            "message": message,
            "status": status
        })

    def start_test(self, client_socket, client_id, test_config):
        """Start test execution"""
        try:
            self.test_running = True
            self.current_test = test_config

            # Broadcast to all clients that test is starting
            self.broadcast_to_all_clients({
                "message": f"Starting test for SN: {test_config['serial_number']}",
                "status": "running"
            })

            # Get the model name
            models = test_config.get('models', [])
            if not models:
                raise ValueError("No model specified in test configuration")

            model_name = models[0]  # Use first model

            # Run test in separate thread
            test_thread = threading.Thread(
                target=self.execute_model_test,
                args=(model_name, test_config),
                daemon=True
            )
            test_thread.start()

        except Exception as e:
            self.test_running = False
            self.current_test = None
            self.send_to_client(client_socket, {
                "message": f"Failed to start test: {e}",
                "status": "error"
            })

    def stop_test(self, client_socket, client_id):
        """Stop current test"""
        self.test_running = False

        self.broadcast_to_all_clients({
            "message": "Test stopped by user request",
            "status": "stopped"
        })

        # If there's a current model instance, it will check is_running_func and stop gracefully
        self.current_test = None

    def execute_model_test(self, model_name, test_config):
        """Execute test for specific model"""
        try:
            # Load the model-specific module
            model_module = self.load_model_module(model_name)

            if not model_module:
                self.broadcast_to_all_clients({
                    "message": f"Model module '{model_name}.py' not found",
                    "status": "error"
                })
                self.test_running = False
                return

            # Create a callback function for the model to send updates
            def status_callback(message, status="running"):
                if self.test_running:  # Only send if test is still running
                    self.broadcast_to_all_clients({
                        "message": message,
                        "status": status
                    })

            # Check if module has the new class-based structure
            model_class_name = f"Model{model_name[-1]}" if model_name.endswith(('A', 'B', 'C')) else model_name

            if hasattr(model_module, model_class_name):
                # Use class-based structure
                self.broadcast_to_all_clients({
                    "message": f"Initializing {model_name} test class...",
                    "status": "running"
                })

                # Get the model class
                model_class = getattr(model_module, model_class_name)

                # Create model instance
                self.current_model_instance = model_class(
                    test_config=test_config,
                    status_callback=status_callback,
                    is_running_func=lambda: self.test_running,
                    server=self
                )

                # Execute Setup
                self.broadcast_to_all_clients({
                    "message": f"Setting up {model_name} test environment...",
                    "status": "running"
                })

                if not self.current_model_instance.setup():
                    self.broadcast_to_all_clients({
                        "message": f"Setup failed for {model_name}",
                        "status": "error"
                    })
                    self.current_model_instance.cleanup()
                    self.test_running = False
                    self.current_model_instance = None
                    return

                # Execute Main tests
                self.broadcast_to_all_clients({
                    "message": f"Executing {model_name} test procedures...",
                    "status": "running"
                })

                success = self.current_model_instance.run_tests()

                # Execute Cleanup
                self.broadcast_to_all_clients({
                    "message": f"Cleaning up {model_name} test environment...",
                    "status": "running"
                })

                self.current_model_instance.cleanup()
                self.current_model_instance = None

                # Handle test completion
                if self.test_running:  # Only if not stopped by user
                    if success:
                        self.broadcast_to_all_clients({
                            "message": f"Test completed successfully for SN: {test_config['serial_number']}",
                            "status": "completed"
                        })
                    else:
                        self.broadcast_to_all_clients({
                            "message": f"Test failed for SN: {test_config['serial_number']}",
                            "status": "error"
                        })

            elif hasattr(model_module, 'run_test'):
                # Use legacy function-based structure
                self.broadcast_to_all_clients({
                    "message": f"Executing {model_name} test procedures (legacy mode)...",
                    "status": "running"
                })

                # Call the model's run_test function
                result = model_module.run_test(test_config, status_callback, lambda: self.test_running, self)

                # Handle test completion
                if self.test_running:  # Only if not stopped by user
                    if result:
                        self.broadcast_to_all_clients({
                            "message": f"Test completed successfully for SN: {test_config['serial_number']}",
                            "status": "completed"
                        })
                    else:
                        self.broadcast_to_all_clients({
                            "message": f"Test failed for SN: {test_config['serial_number']}",
                            "status": "error"
                        })

            else:
                # Neither class nor function found
                self.broadcast_to_all_clients({
                    "message": f"Model module '{model_name}.py' missing test interface (class '{model_class_name}' or function 'run_test')",
                    "status": "error"
                })
                self.test_running = False
                return

            # Reset test state
            self.test_running = False
            self.current_test = None

        except Exception as e:
            self.broadcast_to_all_clients({
                "message": f"Test execution error: {e}",
                "status": "error"
            })

            # Cleanup current model instance if it exists
            if self.current_model_instance:
                try:
                    self.current_model_instance.cleanup()
                except:
                    pass
                self.current_model_instance = None

            self.test_running = False
            self.current_test = None

    def load_model_module(self, model_name):
        """Dynamically load model-specific module"""
        try:
            # Look for model file in current directory
            model_file = f"{model_name}.py"

            if not os.path.exists(model_file):
                print(f"Model file '{model_file}' not found")
                return None

            # Load the module dynamically
            spec = importlib.util.spec_from_file_location(model_name, model_file)
            if spec is None:
                print(f"Could not load spec for {model_file}")
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[model_name] = module
            spec.loader.exec_module(module)

            print(f"Successfully loaded model module: {model_name}")
            return module

        except Exception as e:
            print(f"Error loading model module '{model_name}': {e}")
            return None

    def send_to_client(self, client_socket, message):
        """Send message to specific client"""
        try:
            json_message = json.dumps(message) + '\n'
            client_socket.sendall(json_message.encode('utf-8'))
        except Exception as e:
            print(f"Error sending message to client: {e}")

    def broadcast_to_all_clients(self, message):
        """Send message to all connected clients"""
        disconnected_clients = []

        for client_id, client_info in self.clients.items():
            try:
                self.send_to_client(client_info['socket'], message)
            except Exception as e:
                print(f"Error broadcasting to client {client_id}: {e}")
                disconnected_clients.append(client_id)

        # Remove disconnected clients
        for client_id in disconnected_clients:
            self.disconnect_client(client_id)

    def disconnect_client(self, client_id):
        """Remove client from active connections"""
        if client_id in self.clients:
            try:
                self.clients[client_id]['socket'].close()
            except:
                pass
            del self.clients[client_id]
            print(f"Client {client_id} disconnected")

    def stop_server(self):
        """Stop the server"""
        print("Stopping server...")
        self.running = False
        self.test_running = False

        # Clean up current model instance if running
        if self.current_model_instance:
            try:
                self.current_model_instance.cleanup()
            except:
                pass
            self.current_model_instance = None

        # Close all client connections
        for client_id in list(self.clients.keys()):
            self.disconnect_client(client_id)

        # Close server socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass

        print("Server stopped")

    def cleanup(self):
        """Cleanup resources"""
        self.stop_server()


def main():
    """Main server entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Test Server')
    parser.add_argument('--host', default='localhost', help='Server host (default: localhost)')
    parser.add_argument('--port', type=int, default=5001, help='Server port (default: 5000)')

    args = parser.parse_args()

    server = TestServer(args.host, args.port)

    try:
        server.start_server()
    except KeyboardInterrupt:
        print("\nReceived interrupt signal")
    finally:
        server.stop_server()


if __name__ == "__main__":
    main()