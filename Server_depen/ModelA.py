# ModelA.py - Updated to properly pass is_running_func to TestCases
import time
import random
from test_cases import TestCases


def run_test(test_config, status_callback, is_running_func, server=None):
    """
    Execute Model A specific tests

    Args:
        test_config (dict): Test configuration from client
        status_callback (function): Function to send status updates
        is_running_func (function): Function that returns True if test should continue
        server: Server instance to pass to TestCases (optional)

    Returns:
        bool: True if test passed, False if failed
    """

    try:
        serial_number = test_config.get('serial_number', 'Unknown')
        stages = test_config.get('stages', [])
        temperatures = test_config.get('temperatures', [])
        bands = test_config.get('bands', [])
        test_cases = test_config.get('test_cases', [])

        status_callback(f"[ModelA] Starting test sequence for SN: {serial_number}")
        status_callback(f"[ModelA] Test parameters - Stages: {stages}, Temps: {temperatures}, Bands: {bands}")

        # Initialize Model A specific equipment
        if not initialize_model_a_equipment(status_callback):
            status_callback("[ModelA] ERROR: Failed to initialize equipment", "error")
            return False

        status_callback("[ModelA] Equipment initialized successfully")

        # Initialize TestCases instance
        # Create a mock server object if none provided
        if server is None:
            # Create a simple mock server with the required attributes
            class MockServer:
                def __init__(self):
                    self.running = True
                    self.client_socket = None
                    import threading
                    self.lock = threading.Lock()

            server = MockServer()

        # Pass both server and is_running_func to TestCases
        test_runner = TestCases(server, is_running_func)

        total_tests = len(stages) * len(temperatures) * len(bands) * len(test_cases)
        current_test = 0

        # Execute tests for each combination
        for stage in stages:
            if not is_running_func():
                status_callback("[ModelA] Test stopped by user", "stopped")
                return False

            status_callback(f"[ModelA] Setting up stage: {stage}")
            time.sleep(1)  # Simulate stage setup

            for temperature in temperatures:
                if not is_running_func():
                    status_callback("[ModelA] Test stopped by user", "stopped")
                    return False

                status_callback(f"[ModelA] Setting temperature to {temperature}")
                if not set_temperature_model_a(temperature):
                    status_callback(f"[ModelA] ERROR: Failed to set temperature {temperature}", "error")
                    return False

                # Wait for temperature stabilization
                status_callback(f"[ModelA] Waiting for temperature stabilization at {temperature}")
                # Break the sleep into smaller chunks to allow for stopping
                stabilization_time = 2.0
                sleep_increment = 0.1
                elapsed = 0
                while elapsed < stabilization_time and is_running_func():
                    time.sleep(sleep_increment)
                    elapsed += sleep_increment

                if not is_running_func():
                    status_callback("[ModelA] Test stopped by user", "stopped")
                    return False

                for band in bands:
                    if not is_running_func():
                        status_callback("[ModelA] Test stopped by user", "stopped")
                        return False

                    status_callback(f"[ModelA] Configuring band: {band}")
                    if not configure_band_model_a(band):
                        status_callback(f"[ModelA] ERROR: Failed to configure band {band}", "error")
                        return False

                    for test_case in test_cases:
                        if not is_running_func():
                            status_callback("[ModelA] Test stopped by user", "stopped")
                            return False

                        current_test += 1
                        progress = (current_test / total_tests) * 100

                        status_callback(
                            f"[ModelA] Running test {current_test}/{total_tests} ({progress:.1f}%): {test_case}")

                        # Execute specific test case using TestCases class
                        result = execute_test_case_model_a(status_callback, test_case, stage, temperature, band, test_runner, "ModelA", is_running_func)

                        if not is_running_func():
                            status_callback("[ModelA] Test stopped by user", "stopped")
                            return False

                        if result['passed']:
                            status_callback(f"[ModelA] ✓ {test_case} PASSED - {result['message']}")
                        else:
                            status_callback(f"[ModelA] ✗ {test_case} FAILED - {result['message']}", "error")
                            # For ModelA, continue with other tests even if one fails
                            status_callback("[ModelA] Continuing with remaining tests...")

        # Cleanup
        cleanup_model_a_equipment()
        status_callback(message="[ModelA] Equipment cleanup completed", status="completed")

        status_callback(f"[ModelA] All tests completed for SN: {serial_number}")
        return True

    except Exception as e:
        status_callback(f"[ModelA] Unexpected error: {e}", "error")
        cleanup_model_a_equipment()
        return False


def initialize_model_a_equipment(status_callback):
    """Initialize Model A specific test equipment"""
    print("[ModelA] Initializing signal generator...")
    status_callback("[ModelA] Initializing signal generator...")
    time.sleep(0.5)

    print("[ModelA] Initializing spectrum analyzer...")
    time.sleep(0.5)
    print("[ModelA] Initializing power supply...")
    time.sleep(0.5)
    print("[ModelA] Initializing temperature chamber...")
    time.sleep(0.5)
    return True


def set_temperature_model_a(temperature):
    """Set temperature for Model A testing"""
    print(f"[ModelA] Setting temperature to {temperature}")
    temp_value = int(temperature.replace('C', ''))

    # Simulate temperature setting
    if temp_value < -20 or temp_value > 150:
        print(f"[ModelA] Temperature {temperature} out of range")
        return False

    time.sleep(1)  # Simulate temperature setting time
    return True


def configure_band_model_a(band):
    """Configure frequency band for Model A"""
    print(f"[ModelA] Configuring band: {band}")

    band_configs = {
        'Band1': {'freq_start': 1000, 'freq_stop': 2000, 'power': -10},
        'Band2': {'freq_start': 2000, 'freq_stop': 3000, 'power': -5},
        'Band3': {'freq_start': 3000, 'freq_stop': 4000, 'power': 0}
    }

    if band not in band_configs:
        print(f"[ModelA] Unknown band: {band}")
        return False

    config = band_configs[band]
    print(f"[ModelA] Band config: {config}")
    time.sleep(0.5)  # Simulate configuration time
    return True


def execute_test_case_model_a(status_callback, test_case, stage, temperature, band, test_runner=None, model="ModelA", is_running_func=None):
    """
    Execute specific test case for Model A using TestCases class

    Args:
        status_callback (function): Function to send status updates
        test_case (str): Name of the test case to execute
        stage (str): Test stage
        temperature (str): Temperature setting
        band (str): Frequency band
        test_runner (TestCases): Instance of TestCases class
        model (str): Model identifier
        is_running_func (function): Function that returns True if test should continue

    Returns:
        dict: Test result with 'passed', 'message', and 'execution_time'
    """
    print(f"[ModelA] Executing {test_case} test...")

    start_time = time.time()

    try:
        if test_runner:
            # Use TestCases class methods - NOW ALL METHODS INCLUDE status_callback
            if test_case.lower() == "gain flatness":
                test_runner.test_gain_flatness(model, stage, temperature, band, status_callback)
                passed = True
                message = "Gain flatness test completed successfully"

            elif test_case.lower() == "power sweep":
                test_runner.test_power_sweep(model, stage, temperature, band, status_callback)
                passed = True
                message = "Power sweep test completed successfully"

            elif test_case.lower() == "ampm" or test_case.lower() == "am/pm":
                test_runner.test_am_pm(model, stage, temperature, band, status_callback)
                passed = True
                message = "AM/PM test completed successfully"

            elif test_case.lower() == "spur":
                test_runner.test_spur(model, stage, temperature, band, status_callback)
                passed = True
                message = "Spur test completed successfully"

            else:
                # Fallback to original implementation for unknown test cases
                print(f"[ModelA] Unknown test case '{test_case}', using original implementation")
                return execute_original_test_case(test_case, stage, temperature, band, status_callback, is_running_func)

        else:
            # This should not happen anymore since we create a mock server
            print("[ModelA] No test_runner available, using original implementation")
            return execute_original_test_case(test_case, stage, temperature, band, status_callback, is_running_func)

    except Exception as e:
        passed = False
        message = f"Test execution failed: {str(e)}"
        status_callback(f"[ModelA] ERROR in {test_case}: {str(e)}", "error")

    execution_time = time.time() - start_time

    return {
        'passed': passed,
        'message': message,
        'execution_time': execution_time
    }


def execute_original_test_case(test_case, stage, temperature, band, status_callback, is_running_func=None):
    """
    Original test case execution (fallback method) with stop functionality
    """
    print(f"[ModelA] Executing {test_case} test using original method...")
    status_callback(f"[ModelA] Running {test_case} test (original method)")

    # Simulate test execution time with ability to stop
    execution_time = random.uniform(1, 3)
    sleep_increment = 0.1
    elapsed = 0

    while elapsed < execution_time:
        if is_running_func and not is_running_func():
            return {
                'passed': False,
                'message': 'Test stopped by user',
                'execution_time': elapsed
            }
        time.sleep(sleep_increment)
        elapsed += sleep_increment

    # Test case specific logic
    if test_case == "gain flatness":
        # Simulate gain flatness measurement
        flatness = random.uniform(0.1, 2.0)
        passed = flatness < 1.5
        message = f"Flatness: {flatness:.2f} dB"

    elif test_case == "power sweep":
        # Simulate power sweep test
        power_accuracy = random.uniform(0.05, 0.5)
        passed = power_accuracy < 0.3
        message = f"Power accuracy: ±{power_accuracy:.2f} dB"

    elif test_case == "AMPM":
        # Simulate AM-PM distortion test
        ampm_distortion = random.uniform(0.1, 3.0)
        passed = ampm_distortion < 2.5
        message = f"AM-PM: {ampm_distortion:.2f} deg/dB"

    elif test_case == "spur":
        # Simulate spurious measurement
        spur_level = random.uniform(-80, -40)
        passed = spur_level < -60
        message = f"Spur level: {spur_level:.1f} dBc"

    elif test_case == "phase noise":
        # Simulate phase noise measurement
        phase_noise = random.uniform(-120, -80)
        passed = phase_noise < -100
        message = f"Phase noise: {phase_noise:.1f} dBc/Hz @ 10kHz"

    else:
        # Default test case
        passed = random.choice([True, True, True, False])  # 75% pass rate
        message = f"Generic test result"

    # Send status update for original test completion
    status_callback(f"[ModelA] {test_case}, band:{band} test completed: {message}")

    return {
        'passed': passed,
        'message': message,
        'execution_time': execution_time
    }


def cleanup_model_a_equipment():
    """Cleanup Model A test equipment"""
    print("[ModelA] Shutting down signal generator...")
    time.sleep(0.2)
    print("[ModelA] Shutting down spectrum analyzer...")
    time.sleep(0.2)
    print("[ModelA] Shutting down power supply...")
    time.sleep(0.2)
    print("[ModelA] Equipment cleanup completed")


# Additional Model A specific functions can be added here
def get_model_a_capabilities():
    """Return Model A specific capabilities"""
    return {
        'frequency_range': '1-4 GHz',
        'power_range': '-20 to +10 dBm',
        'temperature_range': '-10 to +75 C',
        'supported_bands': ['Band1', 'Band2', 'Band3'],
        'test_cases': ['gain flatness', 'power sweep', 'AMPM', 'spur', 'phase noise']
    }