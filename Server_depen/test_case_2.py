import time


class TestCases2:
    def __init__(self, server, test_config_dict, is_running_func=None, status_callback=None):
        """
        Initializes the TestCases2 runner.

        Args:
            server: The main server object.
            test_config_dict (dict): A shared dictionary for state management.
            is_running_func (function): A function to check if the test should continue.
            status_callback (function): The function to send status messages back to the client.
        """
        self.server = server
        self.test_config_dict = test_config_dict
        self.is_running_func = is_running_func
        self.status_callback = status_callback if status_callback else self._status_callback_placeholder

    def _status_callback_placeholder(self, message, status="info"):
        """A dummy callback to prevent errors if a real one isn't provided."""
        print(f"INTERNAL STATUS ({status}): {message}")

    def _should_continue(self):
        """Checks if the test sequence has been stopped by the user."""
        if self.is_running_func and not self.is_running_func():
            return False
        return True

    # ==================== NEW PRIMARY ENTRY POINT ====================
    def run_test_by_name(self, test_name, model_name):
        """
        Dynamically calls a test method based on its string name.
        This is the new main entry point from the Model class.

        Args:
            test_name (str): The name of the test case (e.g., "Gain Flatness").
            model_name (str): The name of the model being tested.

        Returns:
            dict: A dictionary with 'passed' (bool) and 'message' (str).
        """
        # Normalize the test name to a method name format (e.g., "Gain Flatness" -> "test_gain_flatness")
        method_name = "test_" + test_name.lower().replace(' ', '_').replace('/', '_')

        # Get the method from this class instance
        test_method = getattr(self, method_name, None)

        if callable(test_method):
            try:
                # Call the found method. It will return True or False.
                passed = test_method()
                message = f"'{test_name}' completed." if passed else f"'{test_name}' failed during execution."
                return {'passed': passed, 'message': message}
            except Exception as e:
                self.status_callback(f"CRITICAL ERROR in {test_name}: {e}", "error")
                return {'passed': False, 'message': f"Execution error in '{test_name}': {e}"}
        else:
            # Fallback for unknown test cases
            message = f"Test case '{test_name}' is not implemented in TestCases2."
            self.status_callback(message, "error")
            return {'passed': False, 'message': message}

    # ==================== REFACTORED TEST CASE METHODS ====================
    def test_gain_flatness(self):
        """
        Runs the full sequence for a Gain Flatness test.
        It now reads all context from self.test_config_dict.

        Returns:
            bool: True if the test passed, False otherwise.
        """
        if not self._should_continue(): return False

        # Pull context from the shared dictionary
        params = self.test_config_dict.get('test_parameters', {})
        model = self.test_config_dict.get('local', {}).get('model_number', 'Unknown')
        stage, temp, band = params.get('stage'), params.get('temperature'), params.get('band')

        self.status_callback(f"Gain Flatness test starting for Model={model}, Stage={stage}, Temp={temp}, Band={band}")

        try:
            self._create_test_case_run()

            # Example of using an instrument
            con_str, ch = self._get_instrument_con_string('power meter output')
            pm_output = self._initialize_instrument(con_str, ch, 'Power Meter')
            if not pm_output:
                # If initialization fails, we must stop and complete the run record as a failure
                self._complete_test_case_run(passed=False)
                return False

            self._get_specs_from_db()
            self._get_measurement_from_db()

            # Simulate taking a measurement and checking it
            measured_value = 0.2  # Simulated value
            self.status_callback(f"Measured Value: {measured_value}")
            passed_status = self._set_measurement_result(measured_value)

            self._complete_test_case_run(passed=passed_status)
            return passed_status
        except Exception as e:
            self.status_callback(f"Error during Gain Flatness: {e}", "error")
            self._complete_test_case_run(passed=False)
            return False

    def test_power_sweep(self):
        """Placeholder for Power Sweep test."""
        self.status_callback("Executing Power Sweep test (placeholder)...")
        time.sleep(0.5)
        return False  # Simulate pass

    def test_am_pm(self):
        """Placeholder for AM/PM test."""
        self.status_callback("Executing AM/PM test (placeholder)...")
        time.sleep(0.5)
        return True  # Simulate pass

    def test_spur(self):
        """Placeholder for Spur test."""
        self.status_callback("Executing Spur test (placeholder)...")
        time.sleep(0.5)
        return True  # Simulate pass

    # ==================== REFACTORED HELPER METHODS ====================
    # Note: `status_callback` is no longer needed as an argument.

    def _create_test_case_run(self):
        # using EXEC dbo.sp_StartTestCaseRun
        # Input TestSeqRunID, TestCaseID, TemperatureID, BandID
        # Output TestCaseRunID
        test_case_run_id = int(time.time() * 1000) % 100000  # Mock ID
        self.status_callback(f'Created Test Case Run Record ID: {test_case_run_id}')
        self.test_config_dict['test_parameters']['test_case_run_id'] = test_case_run_id

    def _complete_test_case_run(self, passed):
        # using EXEC dbo.sp_StopTestCaseRun
        # input TestCaseRUNID, string of 'passed' or 'failed'
        run_id = self.test_config_dict.get('test_parameters', {}).get('test_case_run_id')
        status_str = "passed" if passed else "failed"
        self.status_callback(f"Completing Test Case Run ID: {run_id} with status: {status_str}")

    def _get_instrument_con_string(self, instrument_type):
        # using EXEC dbo.sp_GetInstrumentByType
        # input pc_name and instrument type
        # Output CH and Conn String
        pc_name = self.test_config_dict.get('station', {}).get('pc_name')
        conn_string = "GPIB0::15::INSTR"  # Mock connection string
        ch = 1
        self.status_callback(f"Retrieved for '{instrument_type}': Conn='{conn_string}', CH={ch}")
        return conn_string, ch

    def _initialize_instrument(self, conn_string, ch, instrument_name):
        self.status_callback(f"Initializing {instrument_name}: Conn='{conn_string}', CH={ch}")
        # In a real scenario, you would return a driver object.
        # Here we simulate success/failure.
        if "GPIB" in conn_string:
            return {'name': instrument_name, 'driver': 'mock_driver_object'}  # Simulate success
        else:
            self.status_callback(f"Failed to initialize {instrument_name}", "error")
            return None  # Simulate failure

    def _get_specs_from_db(self):
        # Using EXEC dbo.sp_GetGeneralBandSpec and dbo.sp_GetTestBandSpecs
        spec_dict = {'center_freq': 2500, 'span': '2.5G', 'max_gain_ripple': 0.5}
        self.test_config_dict['local']['spec'] = spec_dict
        self.status_callback(f"Retrieved specs: {spec_dict}")

    def _get_measurement_from_db(self):
        # Using EXEC dbo.sp_GetTestBandMeasurments
        measurement_dict = {
            'full_gain_flatness': {
                'MeasurementID': 101, 'Name': 'Full Band Gain Flatness',
                'HiLimit': 0.5, 'LoLimit': -0.5, 'ComparisonType': 'GELE',
            }
        }
        self.test_config_dict['local']['measurement'] = measurement_dict
        self.status_callback(f"Retrieved measurement definitions.")

    def _set_measurement_result(self, measured_value):
        # using EXEC dbo.sp_SetMeasurementResults
        run_id = self.test_config_dict.get('test_parameters', {}).get('test_case_run_id')
        meas_info = self.test_config_dict['local']['measurement']['full_gain_flatness']
        meas_id = meas_info['MeasurementID']
        hi_limit = meas_info['HiLimit']
        lo_limit = meas_info['LoLimit']

        # Perform comparison
        passed = lo_limit <= measured_value <= hi_limit
        status_str = "Passed" if passed else "Failed"

        self.status_callback(
            f"Setting measurement result for MeasID {meas_id}: Value={measured_value}, Status={status_str}")
        return passed