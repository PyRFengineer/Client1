def add_to_loadlist(self, e):
    selected_cases_controls = [c for c in self.dlg_testcase_list.controls if c.value]
    if not selected_cases_controls:
        return

    temp_id = self.dlg_temp_dd.value
    band_id = self.dlg_band_dd.value

    temp_option = next((opt for opt in self.dlg_temp_dd.options if opt.key == temp_id), None)
    band_option = next((opt for opt in self.dlg_band_dd.options if opt.key == band_id), None)

    if not (temp_option and band_option):
        print("Error: Could not find the selected temperature or band option.")
        return

    temp_name = temp_option.text
    band_name = band_option.text
    case_names = [c.label for c in selected_cases_controls]

    # MODIFICATION: Add 'temperature_id' and 'band_id' to the stored data.
    # These IDs are crucial for looking up the correct execution order rules later.
    self.loadlist_data.append({
        "temperature_id": int(temp_id),
        "temperature": temp_name,
        "band_id": int(band_id),  # UPDATED: Added band_id for use in save_loadlist
        "band": band_name,
        "test_cases": case_names
    })

    self.dlg_datatable.rows.append(
        ft.DataRow(cells=[
            ft.DataCell(ft.Text(temp_name)),
            ft.DataCell(ft.Text(band_name)),
            ft.DataCell(ft.Text(", ".join(case_names), tooltip=", ".join(case_names))),
        ])
    )
    self._safe_page_update()


def save_loadlist(self, e):
    if not self.loadlist_data:
        self.start_btn.disabled = True
        self.close_dialog(self.loadlist_dialog)
        self._safe_page_update()
        return

    # --- Group items by temperature and band to merge duplicates ---
    self.socket_manager._add_output("[Client] Merging loadlist entries...", color=ft.Colors.CYAN)
    merged_data = {}
    for item in self.loadlist_data:
        key = (item['temperature_id'], item['band_id'])
        if key in merged_data:
            merged_data[key]['test_cases'].extend(item['test_cases'])
        else:
            merged_data[key] = item.copy()

    for key in merged_data:
        merged_data[key]['test_cases'] = sorted(list(set(merged_data[key]['test_cases'])))

    self.loadlist_data = list(merged_data.values())

    # --- UPDATED: Sort test cases using specificity-based rule selection ---
    self.socket_manager._add_output("[Client] Organizing test cases by execution order...", color=ft.Colors.CYAN)
    try:
        name_to_id_map = pd.Series(TESTCASE_DEFS_DF.ID.values, index=TESTCASE_DEFS_DF.TestCaseName).to_dict()

        for item in self.loadlist_data:
            band_id = item['band_id']
            temp_id = item['temperature_id']
            tc_name_to_order_map = {}

            # Filter rules for the entire context (Model, Band, Temp) once
            model_match = (TESTCASE_RULES_DF['ModelID'] == self.selected_model_id) | (
                    TESTCASE_RULES_DF['ModelID'] == 0)
            band_match = (TESTCASE_RULES_DF['BandID'] == band_id) | (TESTCASE_RULES_DF['BandID'] == 0)
            temp_match = (TESTCASE_RULES_DF['TemperatureID'] == temp_id) | (TESTCASE_RULES_DF['TemperatureID'] == 0)
            context_rules = TESTCASE_RULES_DF[model_match & band_match & temp_match]

            if context_rules.empty:
                continue

            # For each individual test case, find its single best rule
            for tc_name in item['test_cases']:
                tc_id = name_to_id_map.get(tc_name)
                if tc_id is None:
                    continue

                rules_for_this_tc = context_rules[context_rules['TestCaseID'] == tc_id].copy()

                if not rules_for_this_tc.empty:
                    # Calculate specificity for the applicable rules
                    rules_for_this_tc['specificity_score'] = \
                        (rules_for_this_tc['ModelID'] == self.selected_model_id).astype(int) + \
                        (rules_for_this_tc['BandID'] == band_id).astype(int) + \
                        (rules_for_this_tc['TemperatureID'] == temp_id).astype(int)

                    # Get the single most specific rule
                    highest_specificity = rules_for_this_tc['specificity_score'].max()
                    final_rule = \
                        rules_for_this_tc[rules_for_this_tc['specificity_score'] == highest_specificity].iloc[0]

                    tc_name_to_order_map[tc_name] = final_rule['TCExecutionOrder']

            # Sort the test cases using the order map we built
            item['test_cases'].sort(key=lambda name: tc_name_to_order_map.get(name, float('inf')))

    except Exception as inner_sort_error:
        self.socket_manager._add_output(
            f"[Client] Warning: Could not sort test cases by execution order ({inner_sort_error}).",
            color=ft.Colors.AMBER)

    # --- Sort the entire loadlist by the temperature's execution order ---
    self.socket_manager._add_output("[Client] Organizing loadlist by temperature execution order...",
                                    color=ft.Colors.CYAN)
    try:
        temp_order_map = pd.Series(TEMPERATURES_DF.TempExecution.values, index=TEMPERATURES_DF.ID).to_dict()
        self.loadlist_data.sort(
            key=lambda item: (temp_order_map.get(item['temperature_id'], float('inf')), item['band'])
        )
    except Exception as sort_error:
        self.socket_manager._add_output(
            f"[Client] Warning: Could not sort loadlist by temperature order ({sort_error}).",
            color=ft.Colors.AMBER)
        self.loadlist_data.sort(key=lambda item: (item['temperature'], item['band']))

    print(self.loadlist_data)

    # --- Finalize and update UI ---
    if self.loadlist_data:
        self.start_btn.disabled = False
        self.socket_manager._add_output(
            f"Loadlist created and sorted with {len(self.loadlist_data)} entries. Ready to start.",
            color=ft.Colors.CYAN)
    else:
        self.start_btn.disabled = True

    self.close_dialog(self.loadlist_dialog)
    self._safe_page_update()