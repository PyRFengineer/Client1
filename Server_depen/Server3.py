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

            buffer = ""
            while self.running:
                try:
                    data = client_socket.recv(4096)
                    if not data:
                        break

                    # Handle multiple JSON objects in a single recv
                    buffer += data.decode('utf-8')
                    while '\n' in buffer:
                        message_str, buffer = buffer.split('\n', 1)
                        if message_str.strip():
                            try:
                                message = json.loads(message_str.strip())
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
        """Handle start test command with new loadlist structure"""
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

        # --- MODIFIED: Validate required fields for the new structure ---
        required_fields = ['serial_number', 'model', 'stage', 'loadlist']
        missing_fields = [field for field in required_fields if field not in test_config]

        if missing_fields:
            self.send_to_client(client_socket, {
                "message": f"Missing required fields: {', '.join(missing_fields)}",
                "status": "error"
            })
            return

        # Additional validation for loadlist
        if not isinstance(test_config.get('loadlist'), list) or not test_config.get('loadlist'):
            self.send_to_client(client_socket, {
                "message": "The 'loadlist' must be a non-empty list.",
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

            self.broadcast_to_all_clients({
                "message": f"Starting test for SN: {test_config['serial_number']}",
                "status": "running"
            })

            model_name = test_config.get('model')
            if not model_name:
                raise ValueError("No model specified in test configuration")

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
        self.current_test = None

    def execute_model_test(self, model_name, test_config):
        """
        Execute test for a specific model by iterating through its loadlist.
        """
        overall_success = True
        try:
            model_module = self.load_model_module(model_name)
            if not model_module:
                raise ModuleNotFoundError(f"Model module '{model_name}.py' not found")

            def status_callback(message, status="running"):
                if self.test_running:
                    self.broadcast_to_all_clients({"message": message, "status": status})

            model_class_name = f"Model{model_name[-1]}" if model_name.startswith('Model') and len(model_name) > 5 else model_name
            if not hasattr(model_module, model_class_name):
                 raise AttributeError(f"Model module '{model_name}.py' missing required class '{model_class_name}'")

            model_class = getattr(model_module, model_class_name)
            self.current_model_instance = model_class(
                test_config=test_config,
                status_callback=status_callback,
                is_running_func=lambda: self.test_running,
                server=self
            )

            status_callback(f"Setting up {model_name} test environment...")
            if not self.current_model_instance.setup():
                raise RuntimeError(f"Setup failed for {model_name}")

            # --- NEW: Loop through the loadlist ---
            loadlist = test_config.get('loadlist', [])
            for i, run_item in enumerate(loadlist):
                if not self.test_running:
                    status_callback("Test execution was stopped.", "stopped")
                    overall_success = False
                    break

                temp = run_item.get('temperature', 'N/A')
                band = run_item.get('band', 'N/A')
                status_callback(f"--- Running Loadlist item {i+1}/{len(loadlist)}: Temp={temp}, Band={band} ---")

                # The run_tests method in the model class now receives the specific item
                run_success = self.current_model_instance.run_tests(run_item)

                if not run_success:
                    overall_success = False
                    status_callback(f"Failed item: Temp={temp}, Band={band}", "error")
                    # Decide if you want to stop on first failure or continue
                    # break # Uncomment to stop on first failure

            status_callback(f"Cleaning up {model_name} test environment...")
            self.current_model_instance.cleanup()
            self.current_model_instance = None

            # --- Final Status Report ---
            if self.test_running:
                final_status = "completed" if overall_success else "error"
                final_message = f"Test {'completed successfully' if overall_success else 'finished with errors'} for SN: {test_config['serial_number']}"
                self.broadcast_to_all_clients({"message": final_message, "status": final_status})

        except Exception as e:
            self.broadcast_to_all_clients({"message": f"Test execution error: {e}", "status": "error"})
            if self.current_model_instance:
                try:
                    self.current_model_instance.cleanup()
                except Exception as cleanup_e:
                    print(f"Error during cleanup after failure: {cleanup_e}")
            overall_success = False
        finally:
            self.test_running = False
            self.current_test = None
            self.current_model_instance = None

    def load_model_module(self, model_name):
        """Dynamically load model-specific module"""
        try:
            model_file = f"{model_name}.py"
            if not os.path.exists(model_file):
                print(f"Model file '{model_file}' not found")
                return None
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

        if self.current_model_instance:
            try:
                self.current_model_instance.cleanup()
            except:
                pass
            self.current_model_instance = None

        for client_id in list(self.clients.keys()):
            self.disconnect_client(client_id)

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
    parser.add_argument('--port', type=int, default=5001, help='Server port (default: 5001)')
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