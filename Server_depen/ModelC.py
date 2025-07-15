import os
import time
import random
from test_case_2 import TestCases2


class ModelC:
    def __init__(self, test_config, status_callback, is_running_func, server=None):
        """
        Initializes the ModelC test class.
        This is called once when the test sequence starts.
        """
        self.test_config = test_config
        self.status_callback = status_callback
        self.is_running_func = is_running_func
        self.server = server

        # --- Overall Test Parameters (from initial config) ---
        self.serial_number = test_config.get('serial_number', 'Unknown')
        self.stage = test_config.get('stage', 'Unknown')  # Now a single stage
        self.model = test_config.get('model', 'Unknown')  # Now a single model

        # Test runner instance
        self.test_runner = None
        self.test_results = []

        # This dictionary will hold state and be passed to the test runner
        self.test_config_dict = {
            'local': {},
            'test_parameters': {},
            'station': {}
        }

    # ==================== ONE-TIME SETUP SECTION ====================
    def setup(self):
        """
        Performs one-time setup at the beginning of the entire test sequence.
        This is called only ONCE by the server.
        """
        self.status_callback(f"[ModelC] Initializing test sequence for SN: {self.serial_number}")

        # 1. Get basic info
        self._get_station_info()
        self.test_config_dict['local']['sn'] = self.serial_number
        self.test_config_dict['local']['model_number'] = self.model

        # 2. Initialize test runner
        if not self._setup_test_runner():
            return False

        # 3. Create a single run record for the entire sequence
        self._create_test_seq_run_record()

        # 4. Set station status to active
        self._set_station_active()

        self.status_callback("[ModelC] Setup completed successfully. Ready to execute loadlist.")
        return True

    def _get_station_info(self):
        """Gets station information like PC name."""
        pc_name = os.environ.get('COMPUTERNAME', 'Unknown-PC')
        self.test_config_dict['station']['pc_name'] = pc_name
        self.test_config_dict['station']['chamber_present'] = False  # Placeholder
        self.status_callback(f"Station PC Name: {pc_name}")

    def _setup_test_runner(self):
        """Initializes the TestCases2 instance that runs individual tests."""
        try:
            # OLD line:
            # self.test_runner = TestCases2(self.server, self.test_config_dict, self.is_running_func)

            # NEW line (pass the callback):
            self.test_runner = TestCases2(
                self.server,
                self.test_config_dict,
                self.is_running_func,
                self.status_callback  # Pass the callback here
            )
            self.status_callback("[ModelC] Test runner initialized.")
            return True
        except Exception as e:
            self.status_callback(f"[ModelC] FATAL: Failed to initialize test runner: {e}", "error")
            return False

    def _create_test_seq_run_record(self):
        """Creates a database record for the entire test sequence run."""
        # Mocking EXEC dbo.sp_StartTestSeqRun
        test_seq_run_id = f'TSR-{int(time.time())}'  # Mock ID
        self.status_callback(f"Created Test Sequence Run Record ID: {test_seq_run_id}")
        self.test_config_dict['test_parameters']['test_seq_run_id'] = test_seq_run_id

    def _set_station_active(self):
        """Sets the station status to 'Active' in the database."""
        pc_name = self.test_config_dict.get('station', {}).get('pc_name')
        self.status_callback(f"Setting station '{pc_name}' to 'Active'.")
        # Mocking EXEC dbo.sp_SetStationStatus
        return True

    # ==================== MAIN TEST EXECUTION SECTION ====================
    def run_tests(self, run_item):
        """
        Executes tests for a SINGLE item from the loadlist.
        This method is called REPEATEDLY by the server for each loadlist entry.

        Args:
            run_item (dict): A dictionary containing temperature, band, and test_cases.
                             e.g., {'temperature': '25C', 'band': 'B5', 'test_cases': ['Gain Flatness']}

        Returns:
            bool: True if all tests in this item passed, False otherwise.
        """
        temperature = run_item.get('temperature')
        band = run_item.get('band')
        test_cases_for_run = run_item.get('test_cases', [])

        if not all([temperature, band, test_cases_for_run]):
            self.status_callback(f"Skipping invalid loadlist item: {run_item}", "error")
            return False

        try:
            # --- Setup for this specific run item ---
            if not self._set_and_stabilize_temperature(temperature):
                return False  # Failed to set temp, abort this item

            self.status_callback(f"[ModelC] Configuring for Band: {band}")

            # --- Execute all test cases for this item ---
            all_passed_in_run = True
            total_tests_in_run = len(test_cases_for_run)

            for i, test_case in enumerate(test_cases_for_run):
                if not self.is_running_func():
                    self.status_callback("[ModelC] Test stopped by user.", "stopped")
                    return False

                progress = ((i + 1) / total_tests_in_run) * 100
                self.status_callback(f"[ModelC] Running {i + 1}/{total_tests_in_run} ({progress:.0f}%): {test_case}")

                # Execute the single test and check its result
                test_passed = self._execute_single_test(temperature, band, test_case)
                if not test_passed:
                    all_passed_in_run = False
                    # Decide whether to stop on first failure or continue
                    # For ModelC, we continue even if one fails.

            return all_passed_in_run

        except Exception as e:
            self.status_callback(f"[ModelC] Critical error during run for Temp={temperature}, Band={band}: {e}",
                                 "error")
            return False

    def _set_and_stabilize_temperature(self, temperature):
        """Sets temperature and waits for it to stabilize."""
        self.status_callback(f"[ModelC] Setting temperature to {temperature}")
        # Simulate setting temp
        if not self.is_running_func(): return False

        self.status_callback(f"[ModelC] Waiting for temperature to stabilize at {temperature}...")
        # Simulate stabilization time, checking for stop signal
        for _ in range(5):  # Simulate 2.5 second wait
            if not self.is_running_func(): return False
            time.sleep(0.5)

        self.status_callback(f"[ModelC] Temperature stabilized at {temperature}.")
        return True

    def _execute_single_test(self, temperature, band, test_case):
        """Executes a single test case and reports its result."""
        # Populate the dictionary that the test runner will use
        self.test_config_dict['test_parameters']['stage'] = self.stage
        self.test_config_dict['test_parameters']['temperature'] = temperature
        self.test_config_dict['test_parameters']['band'] = band
        self.test_config_dict['test_parameters']['test_case'] = test_case

        # Run the specific test case via the test runner
        result = self.test_runner.run_test_by_name(test_case, self.model)

        # Store detailed result
        self.test_results.append({
            'stage': self.stage,
            'temperature': temperature,
            'band': band,
            'test_case': test_case,
            'result': result
        })

        # Report result to the client
        if result['passed']:
            self.status_callback(f"[ModelC] ✓ {test_case} PASSED - {result['message']}")
        else:
            self.status_callback(f"[ModelC] ✗ {test_case} FAILED - {result['message']}", "error")

        return result['passed']

    # ==================== ONE-TIME CLEANUP SECTION ====================
    def cleanup(self):
        """
        Performs one-time cleanup at the end of the entire test sequence.
        This is called only ONCE by the server after all loadlist items are processed.
        """
        self.status_callback("[ModelC] Test sequence finished. Performing cleanup.")
        self._complete_test_seq_run_record()
        self.status_callback("[ModelC] Cleanup complete.")

    def _complete_test_seq_run_record(self):
        """Closes the database record for the test sequence run."""
        test_seq_run_id = self.test_config_dict.get('test_parameters', {}).get('test_seq_run_id')
        if test_seq_run_id:
            self.status_callback(f"Completing Test Sequence Run Record ID: {test_seq_run_id}")
            # Mocking EXEC dbo.sp_StopTestSeqRun
        return True