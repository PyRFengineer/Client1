# Client
import flet as ft
import socket
import json
import threading
import configparser
import time
import pandas as pd
import os
import sys

# --- DATA LOADING SECTION ---
# All data is now loaded from an external Excel file using an ID-based structure.
# Run create_test_data_excel.py first to generate this file.

EXCEL_FILE = r"C:\Project\ClientS\Server_depen\test_data.xlsx"
try:
    all_data = pd.read_excel(EXCEL_FILE, sheet_name=None)
    MODELS_DF = all_data['Models']
    STAGES_DF = all_data['Stages']
    BANDS_DF = all_data['Bands']
    TEMPERATURES_DF = all_data['Temperatures']
    TESTCASE_DEFS_DF = all_data['TestCaseDefinitions']
    TESTCASE_RULES_DF = all_data['TestCaseRules']
    print(f"Successfully loaded ID-based data from '{EXCEL_FILE}'.")
except FileNotFoundError:
    print(f"FATAL ERROR: The data file '{EXCEL_FILE}' was not found.")
    print("Please run the `create_test_data_excel.py` script first to generate it.")
    sys.exit(1)
except Exception as e:
    print(f"FATAL ERROR: Could not read data from '{EXCEL_FILE}'. Error: {e}")
    sys.exit(1)


# --- NEW ID-BASED DATA ACCESS FUNCTIONS ---

def get_model():
    """Returns the DataFrame of all models."""
    return MODELS_DF.copy()


def get_stage(model_id):
    """Filters and returns stages for a given model_id."""
    return STAGES_DF[STAGES_DF['ModelID'] == model_id][['ID', 'StageName']].copy()


def get_band(model_id):
    """Filters and returns bands for a given model_id."""
    return BANDS_DF[BANDS_DF['ModelID'] == model_id][['ID', 'BandName']].copy()


def get_temperature(stage_id):
    """Filters and returns temperatures for a given stage_id."""
    return TEMPERATURES_DF[TEMPERATURES_DF['StageID'] == stage_id][['ID', 'TemperatureName']].copy()


def get_testcase(model_id, band_id, temperature_id):
    """
    Finds the correct test cases based on a priority system in the rules table using IDs.
    A value of 0 in the rules table is treated as a wildcard.
    """
    # Find all rules that could possibly match, including wildcards (ID=0)
    model_match = (TESTCASE_RULES_DF['ModelID'] == model_id) | (TESTCASE_RULES_DF['ModelID'] == 0)
    band_match = (TESTCASE_RULES_DF['BandID'] == band_id) | (TESTCASE_RULES_DF['BandID'] == 0)
    temp_match = (TESTCASE_RULES_DF['TemperatureID'] == temperature_id) | (TESTCASE_RULES_DF['TemperatureID'] == 0)

    applicable_rules = TESTCASE_RULES_DF[model_match & band_match & temp_match]

    if applicable_rules.empty:
        return pd.DataFrame({"ID": [], "TestCaseName": []})

    # Find the highest priority (lowest number) among the matching rules
    highest_priority = applicable_rules['Priority'].min()

    # Get all TestCaseIDs associated with that highest priority rule
    winning_rule_tcs = applicable_rules[applicable_rules['Priority'] == highest_priority]
    test_case_ids = winning_rule_tcs['TestCaseID'].unique()

    # Look up the details for these test cases from the definitions table
    final_test_cases = TESTCASE_DEFS_DF[TESTCASE_DEFS_DF['ID'].isin(test_case_ids)].copy()

    return final_test_cases[['ID', 'TestCaseName']]


# --- SocketManager Class (unchanged) ---
class SocketManager:
    # ... (code is identical to your previous version)
    def __init__(self, output_list, status_indicator, page):
        self.client_socket = None
        self.receive_thread = None
        self.running = False
        self.buffer = ""
        self.socket_lock = threading.Lock()
        self.output_list = output_list
        self.status_indicator = status_indicator
        self.page = page
        self.config = configparser.ConfigParser()
        self.config.read('servers.ini')
        self.auto_scroll_checkbox = None
        self.last_server = None
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 3

    def connect_to_server(self, server_name):
        with self.socket_lock:
            if self.client_socket:
                try:
                    self.client_socket.close()
                except Exception as e:
                    print(f"Error closing previous socket: {e}")
                self.client_socket = None
            self.running = False
            self.reconnect_attempts = 0

        if not server_name:
            self._add_output("Please select a server", color=ft.Colors.RED)
            self.status_indicator.bgcolor = ft.Colors.GREY
            self._safe_page_update()
            return False

        try:
            host = self.config[server_name]['host']
            port = int(self.config[server_name]['port'])
        except KeyError:
            self._add_output(f"Server '{server_name}' not found in servers.ini", color=ft.Colors.RED)
            self.status_indicator.bgcolor = ft.Colors.GREY
            self._safe_page_update()
            return False

        try:
            with self.socket_lock:
                self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.client_socket.settimeout(5)
                self.client_socket.connect((host, port))
                self._add_output(f"Connected to {server_name} ({host}:{port})", color=ft.Colors.GREEN)
                print(f"Connected to {server_name} ({host}:{port})")
                self.status_indicator.bgcolor = ft.Colors.YELLOW
                self.running = True
                self.buffer = ""
                if not self.receive_thread or not self.receive_thread.is_alive():
                    self.receive_thread = threading.Thread(target=self.receive_messages, daemon=True)
                    self.receive_thread.start()
                self.last_server = server_name
            self._safe_page_update()
            return True
        except Exception as e:
            with self.socket_lock:
                if self.client_socket:
                    try:
                        self.client_socket.close()
                    except:
                        pass
                self.client_socket = None
            self._add_output(f"Connection error to {server_name}: {e}", color=ft.Colors.RED)
            self.status_indicator.bgcolor = ft.Colors.GREY
            self._safe_page_update()
            print(f"Connection error to {server_name}: {e}")
            return False

    def receive_messages(self):
        print("Receive thread starting...")
        while self.running:
            with self.socket_lock:
                if not self.client_socket:
                    time.sleep(0.1)
                    continue
                current_socket = self.client_socket

            try:
                data = current_socket.recv(4096)
                if not data:
                    raise socket.error("Server closed connection")

                decoded_chunk = data.decode('utf-8', errors='replace')
                print(f"Received raw data: {decoded_chunk}")
                self.buffer += decoded_chunk
                self.process_buffer()

            except socket.timeout:
                continue
            except socket.error as e:
                print(f"Socket receive error: {e}")
                with self.socket_lock:
                    if self.client_socket == current_socket:
                        self._add_output(f"Receive error: {e}. Disconnected.", color=ft.Colors.RED)
                        self.status_indicator.bgcolor = ft.Colors.GREY
                        try:
                            current_socket.close()
                        except:
                            pass
                        self.client_socket = None
                self._safe_page_update()

                if self.running and self.last_server and self.reconnect_attempts < self.max_reconnect_attempts:
                    self.reconnect_attempts += 1
                    print(
                        f"Attempting to reconnect to {self.last_server} (Attempt {self.reconnect_attempts}/{self.max_reconnect_attempts})...")
                    time.sleep(2)
                    if self.running:
                        self.connect_to_server(self.last_server)
                else:
                    self.running = False
                    break
            except Exception as e:
                print(f"Unexpected error in receive loop: {e}")
                self.running = False
                break

        print("Receive thread stopped.")
        if self.running:
            with self.socket_lock:
                if not self.client_socket:
                    self.status_indicator.bgcolor = ft.Colors.GREY
                    self._safe_page_update()

    def process_buffer(self):
        start_pos = 0
        while start_pos < len(self.buffer):
            try:
                decoder = json.JSONDecoder()
                obj, end_pos = decoder.raw_decode(self.buffer[start_pos:])
                self.handle_message(obj)
                start_pos += end_pos
                while start_pos < len(self.buffer) and self.buffer[start_pos].isspace():
                    start_pos += 1
            except json.JSONDecodeError:
                if len(self.buffer) - start_pos > 1000:
                    print("Warning: Large unparseable buffer detected, clearing excess")
                    self.buffer = self.buffer[-500:]
                    start_pos = 0
                else:
                    next_open_brace = self.buffer.find('{', start_pos + 1)
                    if next_open_brace != -1:
                        start_pos = next_open_brace
                    else:
                        break
        if start_pos > 0:
            self.buffer = self.buffer[start_pos:]

    def handle_message(self, decoded_data):
        print(f"Processing decoded message: {decoded_data}")
        message = decoded_data.get('message', 'No message field')

        status = decoded_data.get("status")
        if status in ["stopped", "error", "Failed"]:
            self._add_output(message, color=ft.Colors.RED)
        else:
            self._add_output(message, color=ft.Colors.BLUE)

        status = decoded_data.get("status")
        if status == "idle":
            self.status_indicator.bgcolor = ft.Colors.ORANGE_100
        elif status == "running":
            self.status_indicator.bgcolor = ft.Colors.RED
        elif status == "completed":
            self.status_indicator.bgcolor = ft.Colors.GREEN_ACCENT_700
        elif status in ["stopped", "error", "Failed"]:
            self.status_indicator.bgcolor = ft.Colors.AMBER
        else:
            self.status_indicator.bgcolor = ft.Colors.YELLOW
        self._safe_page_update()

    def send_message(self, message):
        with self.socket_lock:
            if not self.client_socket:
                self._add_output("No active connection to send message.", color=ft.Colors.RED)
                self._safe_page_update()
                return False
            try:
                self.client_socket.sendall(json.dumps(message).encode() + b'\n')
                print(f"Sent message: {message}")
                return True
            except Exception as e:
                self._add_output(f"Send error: {e}", color=ft.Colors.RED)
                self.status_indicator.bgcolor = ft.Colors.GREY
                self._safe_page_update()
                print(f"Send error: {e}")
                return False

    def start_listening(self):
        with self.socket_lock:
            if self.client_socket and self.running:
                if not self.receive_thread or not self.receive_thread.is_alive():
                    print("Receive thread was not alive, restarting.")
                    self.receive_thread = threading.Thread(target=self.receive_messages, daemon=True)
                    self.receive_thread.start()
                return True
            elif self.client_socket and not self.running:
                self.running = True
                self.receive_thread = threading.Thread(target=self.receive_messages, daemon=True)
                self.receive_thread.start()
                return True
        return False

    def stop(self):
        print("SocketManager stop called.")
        was_running = self.running
        self.running = False

        thread_to_join = None
        with self.socket_lock:
            if self.client_socket:
                try:
                    self.client_socket.close()
                except Exception as e:
                    print(f"Error closing socket during stop: {e}")
                self.client_socket = None
            thread_to_join = self.receive_thread

        if thread_to_join and thread_to_join.is_alive():
            print("Waiting for receive thread to join...")
            thread_to_join.join(timeout=1.0)
            if thread_to_join.is_alive():
                print("Receive thread did not terminate gracefully.")

        self.receive_thread = None
        if was_running:
            self._add_output("Socket manager stopped. Connection closed.", color=ft.Colors.AMBER)
            self.status_indicator.bgcolor = ft.Colors.GREY
            self._safe_page_update()
        print("SocketManager fully stopped.")

    def _add_output(self, text, color=None):
        text_control = ft.Text(text, color=color)
        self.output_list.controls.append(text_control)
        self._safe_page_update()
        if self.auto_scroll_checkbox and self.auto_scroll_checkbox.value:
            try:
                self.output_list.scroll_to(offset=-1, duration=100)
            except Exception as e:
                print(f"Auto-scroll error: {e}")

    def _safe_page_update(self):
        try:
            self.page.update()
        except Exception as e:
            print(f"Error updating page: {e}")


# --- SelectionDropdown Class (unchanged) ---
class SelectionDropdown:
    # ... (code is identical to your previous version)
    def __init__(self, title, page):
        self.page = page
        self.title = title
        self.checkboxes = []
        self.selected_items = []
        self.selected_ids = {}
        self.on_selection_change = None

        self.selected_text = ft.Text(
            f"No {title.lower()} selected",
            width=180,
            no_wrap=True,
            tooltip=f"No {title.lower()} selected"
        )
        self.dropdown_container = ft.Container(
            content=ft.Column(
                [],
                tight=True,
                spacing=5,
                scroll=ft.ScrollMode.ADAPTIVE,
                height=150
            ),
            border=ft.border.all(1, ft.Colors.OUTLINE),
            border_radius=5,
            padding=10,
            bgcolor=ft.Colors.SURFACE,
            visible=False
        )
        self.dropdown_btn = ft.ElevatedButton(
            f"Select {title}",
            icon=ft.Icons.ARROW_DROP_DOWN,
            on_click=self.toggle_dropdown,
            width=200
        )
        self.dropdown_column = ft.Column(
            [self.dropdown_btn, self.selected_text, self.dropdown_container],
            spacing=5
        )

    def toggle_dropdown(self, e):
        self.dropdown_container.visible = not self.dropdown_container.visible
        self._safe_page_update()

    def update_selected_items(self, e):
        self.selected_items = [cb.label for cb in self.checkboxes if cb.value]
        self.selected_ids = {cb.label: cb.id for cb in self.checkboxes if cb.value and hasattr(cb, 'id')}

        selected_str = f"No {self.title.lower()} selected"
        if self.selected_items:
            selected_str = f"Selected: {', '.join(self.selected_items)}"

        self.selected_text.value = selected_str
        self.selected_text.tooltip = selected_str
        if len(selected_str) > (self.selected_text.width / 8 if self.selected_text.width else 22):
            self.selected_text.value = selected_str[:int(
                self.selected_text.width / 8 if self.selected_text.width else 22) - 3] + "..."

        self._safe_page_update()
        if self.on_selection_change:
            self.on_selection_change()

    def set_items(self, items, ids=None):
        self.checkboxes = []
        for idx, item_label in enumerate(items):
            cb = ft.Checkbox(label=item_label, value=False)
            if ids:
                if isinstance(ids, dict):
                    cb.id = ids.get(item_label)
                elif isinstance(ids, list) and idx < len(ids):
                    cb.id = ids[idx]
            cb.on_change = self.update_selected_items
            self.checkboxes.append(cb)

        self.dropdown_container.content.controls = self.checkboxes
        self.selected_items = []
        self.selected_ids = {}
        no_selection_str = f"No {self.title.lower()} selected"
        self.selected_text.value = no_selection_str
        self.selected_text.tooltip = no_selection_str
        self._safe_page_update()

    def _safe_page_update(self):
        try:
            self.page.update()
        except Exception as e:
            print(f"Error updating page in SelectionDropdown: {e}")


# --- TestController Class (UPDATED with Loadlist sorting) ---
class TestController:
    def __init__(self, page: ft.Page):
        self.page = page
        self.min_left_panel_width = 180
        self.max_left_panel_width = 500
        self.initial_left_panel_width = 280

        self.setup_page()
        self.create_widgets()
        self.socket_manager = SocketManager(self.output_list, self.status_indicator, self.page)
        self.socket_manager.auto_scroll_checkbox = self.auto_scroll_checkbox
        self.setup_layout()
        self.register_event_handlers()

        # --- State variables ---
        self.selected_model_name = None
        self.selected_model_id = None
        self.selected_stage_name = None
        self.selected_stage_id = None
        self.loadlist_data = []  # This will store the configured loadlist

        # Add dialogs to the page overlay
        self.page.overlay.append(self.sn_dialog)
        self.page.overlay.append(self.loadlist_dialog)

    def setup_page(self):
        self.page.title = "Test Controller"
        self.page.vertical_alignment = ft.MainAxisAlignment.START
        self.page.padding = 0

    def create_widgets(self):
        config = configparser.ConfigParser()
        ini_file = 'servers.ini'

        if not os.path.exists(ini_file):
            config['ServerDefault'] = {'host': 'localhost', 'port': '9999'}
            with open(ini_file, 'w') as configfile:
                config.write(configfile)
        else:
            config.read(ini_file)
        servers = list(config.sections()) or ['No Servers']

        model_data = get_model()
        models = model_data["ModelName"].tolist()

        # --- Main window widgets ---
        self.server_dd = ft.Dropdown(
            label="Select Server", options=[ft.dropdown.Option(s) for s in servers],
            width=200, value=servers[0] if servers else None
        )
        self.model_dd = ft.Dropdown(
            label="Select Model", options=[ft.dropdown.Option(m) for m in models], width=200
        )
        self.stage_dropdown = SelectionDropdown("Stage", self.page)

        self.output_list = ft.ListView(expand=True, auto_scroll=False, padding=5)
        self.output_container = ft.Container(
            content=self.output_list, border=ft.border.all(1, ft.Colors.OUTLINE),
            border_radius=5, padding=5, expand=True
        )

        self.auto_scroll_checkbox = ft.Checkbox(label="Auto-scroll", value=True)
        self.status_indicator = ft.Container(
            width=20, height=20, border_radius=10, bgcolor=ft.Colors.GREY,
            animate=ft.Animation(300, ft.AnimationCurve.EASE)
        )

        # --- Buttons ---
        self.loadlist_btn = ft.ElevatedButton("Build Loadlist", on_click=self.open_loadlist_dialog,
                                              icon=ft.Icons.LIST_ALT, disabled=True)
        self.start_btn = ft.ElevatedButton("Start Test", on_click=self.show_sn_dialog, icon=ft.Icons.PLAY_ARROW,
                                           bgcolor=ft.Colors.GREEN_400, disabled=True)
        self.stop_btn = ft.ElevatedButton("Stop Test", on_click=self.stop_test, icon=ft.Icons.STOP, disabled=True,
                                          bgcolor=ft.Colors.RED_400)
        self.clear_btn = ft.ElevatedButton("Clear Output", on_click=self.clear_output, icon=ft.Icons.CLEAR_ALL)
        self.connect_btn = ft.ElevatedButton("Connect", on_click=self.connect_or_resume, icon=ft.Icons.LINK)

        # --- Loadlist Dialog Widgets ---
        self.create_loadlist_dialog_widgets()

        # --- Serial Number Dialog ---
        self.serial_number = ft.Ref[ft.TextField]()
        self.sn_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Serial Number Required"),
            content=ft.Column([
                ft.Text("Please enter the Serial Number:"),
                ft.TextField(ref=self.serial_number, label="SN#", autofocus=True)
            ], tight=True, spacing=10),
            actions=[ft.TextButton("Submit", on_click=self.start_test_with_sn)],
            actions_alignment=ft.MainAxisAlignment.END
        )

        self.left_panel_container = ft.Container(
            width=self.initial_left_panel_width, padding=10, border_radius=ft.border_radius.all(5)
        )

    def create_loadlist_dialog_widgets(self):
        # Widgets that will go inside the loadlist dialog
        self.dlg_temp_dd = ft.Dropdown(label="Select Temperature", width=250, on_change=self.on_dialog_selection_change)
        self.dlg_band_dd = ft.Dropdown(label="Select Band", width=250, on_change=self.on_dialog_selection_change)
        self.dlg_testcase_list = ft.ListView(spacing=5, height=150, expand=False)
        self.dlg_add_btn = ft.ElevatedButton("Add to Loadlist", icon=ft.Icons.ADD, on_click=self.add_to_loadlist,
                                             disabled=True)
        self.dlg_datatable = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Temp")),
                ft.DataColumn(ft.Text("Band")),
                ft.DataColumn(ft.Text("Test Cases")),
            ],
            rows=[]
        )

        # The dialog itself
        self.loadlist_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Build Test Loadlist"),
            content=ft.Column([
                ft.Row([self.dlg_temp_dd, self.dlg_band_dd], spacing=10),
                ft.Text("Available Test Cases:"),
                ft.Container(self.dlg_testcase_list, border=ft.border.all(1, ft.Colors.OUTLINE), padding=5),
                ft.Row([self.dlg_add_btn], alignment=ft.MainAxisAlignment.END),
                ft.Divider(),
                ft.Text("Current Loadlist:"),
                ft.Container(ft.Column([self.dlg_datatable], scroll=ft.ScrollMode.ADAPTIVE, height=200),
                             border=ft.border.all(1, ft.Colors.OUTLINE), padding=5)
            ], width=600, spacing=10),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: self.close_dialog(self.loadlist_dialog)),
                ft.ElevatedButton("Save Loadlist", icon=ft.Icons.SAVE, on_click=self.save_loadlist)
            ],
            actions_alignment=ft.MainAxisAlignment.END
        )

    def move_vertical_divider(self, e: ft.DragUpdateEvent):
        new_width = self.left_panel_container.width + e.delta_x
        if self.min_left_panel_width <= new_width <= self.max_left_panel_width:
            self.left_panel_container.width = new_width
            self._safe_page_update()

    def show_draggable_cursor(self, e: ft.HoverEvent):
        e.control.mouse_cursor = ft.MouseCursor.RESIZE_LEFT_RIGHT
        e.control.update()

    def setup_layout(self):
        # LEFT PANEL
        left_panel_content_column = ft.Column(
            controls=[
                ft.Text("Server Configuration", weight=ft.FontWeight.BOLD, style=ft.TextThemeStyle.TITLE_MEDIUM),
                self.server_dd,
                ft.Divider(height=10, thickness=1),
                ft.Text("Test Parameters", weight=ft.FontWeight.BOLD, style=ft.TextThemeStyle.TITLE_MEDIUM),
                self.model_dd,
                self.stage_dropdown.dropdown_column,
                ft.Divider(height=10, thickness=1),
                self.loadlist_btn
            ],
            scroll=ft.ScrollMode.ADAPTIVE,
            spacing=10,
            expand=True
        )
        self.left_panel_container.content = left_panel_content_column

        # RIGHT PANEL
        right_panel_content_column = ft.Column(
            controls=[
                ft.Row(
                    [self.start_btn, self.stop_btn, self.clear_btn, self.connect_btn],
                    alignment=ft.MainAxisAlignment.START,
                    spacing=10,
                    wrap=True
                ),
                ft.Divider(height=10, thickness=1),
                ft.Text("Output Log", weight=ft.FontWeight.BOLD, style=ft.TextThemeStyle.TITLE_MEDIUM),
                self.output_container,
                ft.Row(
                    [self.auto_scroll_checkbox, self.status_indicator],
                    alignment=ft.MainAxisAlignment.END,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=10
                )
            ],
            spacing=10,
            expand=True
        )
        right_panel_outer_container = ft.Container(
            content=right_panel_content_column,
            padding=10,
            border_radius=ft.border_radius.all(5),
            expand=True
        )

        # Main Layout
        main_layout_row = ft.Row(
            controls=[
                self.left_panel_container,
                ft.GestureDetector(
                    content=ft.VerticalDivider(thickness=2, color=ft.Colors.OUTLINE),
                    drag_interval=5, on_pan_update=self.move_vertical_divider, on_hover=self.show_draggable_cursor
                ),
                right_panel_outer_container
            ],
            spacing=0,
            expand=True
        )
        self.page.add(main_layout_row)

    def register_event_handlers(self):
        self.model_dd.on_change = self.on_model_change
        self.server_dd.on_change = self.connect_to_server_action
        self.stage_dropdown.on_selection_change = self.on_stage_change

    def update_stop_button_state(self):
        is_connected_and_running = bool(self.socket_manager.client_socket and self.socket_manager.running)
        if self.stop_btn.disabled != (not is_connected_and_running):
            self.stop_btn.disabled = not is_connected_and_running
            self._safe_page_update()

    def on_model_change(self, e):
        self.selected_model_name = self.model_dd.value
        model_row = MODELS_DF[MODELS_DF['ModelName'] == self.selected_model_name]
        self.selected_model_id = model_row['ID'].iloc[0] if not model_row.empty else None

        self.stage_dropdown.set_items([])
        self.loadlist_btn.disabled = True
        self.start_btn.disabled = True
        self.loadlist_data = []

        if self.selected_model_id is not None:
            stage_data = get_stage(self.selected_model_id)
            if not stage_data.empty:
                self.stage_dropdown.set_items(
                    stage_data["StageName"].tolist(),
                    {row["StageName"]: row["ID"] for _, row in stage_data.iterrows()}
                )
        self._safe_page_update()

    def on_stage_change(self):
        if len(self.stage_dropdown.selected_items) == 1:
            self.loadlist_btn.disabled = False
            self.selected_stage_name = self.stage_dropdown.selected_items[0]
            self.selected_stage_id = list(self.stage_dropdown.selected_ids.values())[0]
        else:
            self.loadlist_btn.disabled = True
            self.selected_stage_name = None
            self.selected_stage_id = None

        self.start_btn.disabled = True
        self.loadlist_data = []
        self._safe_page_update()

    def open_loadlist_dialog(self, e):
        self.loadlist_data = []
        self.dlg_datatable.rows.clear()
        self.dlg_testcase_list.controls.clear()
        self.dlg_add_btn.disabled = True

        temp_data = get_temperature(self.selected_stage_id)
        temp_options = [ft.dropdown.Option(key=str(row['ID']), text=row['TemperatureName']) for _, row in
                        temp_data.iterrows()]
        self.dlg_temp_dd.options = temp_options
        self.dlg_temp_dd.value = None

        band_data = get_band(self.selected_model_id)
        band_options = [ft.dropdown.Option(key=str(row['ID']), text=row['BandName']) for _, row in band_data.iterrows()]
        self.dlg_band_dd.options = band_options
        self.dlg_band_dd.value = None

        self.loadlist_dialog.open = True
        self._safe_page_update()

    def on_dialog_selection_change(self, e):
        self.dlg_testcase_list.controls.clear()
        self.dlg_add_btn.disabled = True

        temp_id = self.dlg_temp_dd.value
        band_id = self.dlg_band_dd.value

        if self.selected_model_id and temp_id and band_id:
            test_case_data = get_testcase(self.selected_model_id, int(band_id), int(temp_id))
            if not test_case_data.empty:
                for _, row in test_case_data.iterrows():
                    cb = ft.Checkbox(label=row['TestCaseName'], data=row['ID'])
                    self.dlg_testcase_list.controls.append(cb)
                self.dlg_add_btn.disabled = False
        self._safe_page_update()

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

        # MODIFICATION: Add 'temperature_id' to the stored data.
        # This ID is the crucial link to the 'Temperatures' table.
        self.loadlist_data.append({
            "temperature_id": int(temp_id),  # <-- THIS LINE IS ESSENTIAL
            "temperature": temp_name,
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
        # --- NEW: Sort the loadlist by TempExecution order ---
        if self.loadlist_data:
            self.socket_manager._add_output("[Client] Organizing loadlist by temperature execution order...",
                                            color=ft.Colors.CYAN)
            try:
                # 1. Create a "lookup map" from the main Temperatures table.
                #    This map will connect each temperature ID to its execution order.
                #    Example: {101: 1, 102: 3, 103: 2} where the key is ID and value is TempExecution.
                temp_order_map = pd.Series(TEMPERATURES_DF.TempExecution.values, index=TEMPERATURES_DF.ID).to_dict()

                # 2. Sort the `loadlist_data` using the lookup map.
                #    For each item in the list, the `key` function does the following:
                #      a. It gets the item's 'temperature_id'.
                #      b. It uses that ID to look up the 'TempExecution' order from the map.
                #      c. It uses that execution order as the primary sorting value.
                self.loadlist_data.sort(
                    key=lambda item: (temp_order_map.get(item['temperature_id']), item['band'])
                )

            except Exception as sort_error:
                self.socket_manager._add_output(
                    f"[Client] Warning: Could not sort by execution order ({sort_error}). Falling back to name sort.",
                    color=ft.Colors.AMBER)
                # Fallback to a simple alphabetic sort if the advanced sort fails
                self.loadlist_data.sort(key=lambda item: (item['temperature'], item['band']))
        print(self.loadlist_data)
        # --- Existing logic continues below ---
        if self.loadlist_data:
            self.start_btn.disabled = False
            self.socket_manager._add_output(
                f"Loadlist created and sorted with {len(self.loadlist_data)} entries. Ready to start.",
                color=ft.Colors.CYAN)
        else:
            self.start_btn.disabled = True

        self.close_dialog(self.loadlist_dialog)
        self._safe_page_update()

    def close_dialog(self, dialog):
        dialog.open = False
        self._safe_page_update()

    def connect_to_server_action(self, e=None):
        if self.server_dd.value:
            self.socket_manager.connect_to_server(self.server_dd.value)
            self.update_stop_button_state()
        else:
            self.socket_manager._add_output("No server selected.", color=ft.Colors.RED)
            self._safe_page_update()

    def show_sn_dialog(self, e):
        self.serial_number.current.value = ""
        self.serial_number.current.error_text = None
        self.sn_dialog.open = True
        self._safe_page_update()

    def start_test_with_sn(self, e):
        sn_val = self.serial_number.current.value
        if not sn_val:
            self.serial_number.current.error_text = "Serial Number is required."
            self.serial_number.current.update()
            return

        self.sn_dialog.open = False
        self._safe_page_update()

        if not self.socket_manager.client_socket:
            self.socket_manager._add_output("Not connected. Attempting to connect...", color=ft.Colors.YELLOW)
            if not self.socket_manager.connect_to_server(self.server_dd.value):
                self.socket_manager._add_output("Connection failed. Test not started.", color=ft.Colors.RED)
                self.update_stop_button_state()
                return
            time.sleep(0.2)
        self.update_stop_button_state()

        test_config_payload = {
            "serial_number": sn_val,
            "model": self.selected_model_name,
            "stage": self.selected_stage_name,
            "loadlist": self.loadlist_data
        }

        if self.socket_manager.send_message({"command": "start", "test_config": test_config_payload}):
            self.socket_manager._add_output(
                f"Test started for SN#: {sn_val} with {len(self.loadlist_data)} configurations.",
                color=ft.Colors.GREEN)
        else:
            self.socket_manager._add_output(f"Failed to send start command for SN#: {sn_val}", color=ft.Colors.RED)
        self._safe_page_update()

    def stop_test(self, e):
        if self.socket_manager.send_message({"command": "stop"}):
            self.socket_manager._add_output("Stop command sent.", color=ft.Colors.AMBER)
        else:
            self.socket_manager._add_output("Failed to send stop command (not connected?).", color=ft.Colors.RED)
        self._safe_page_update()

    def clear_output(self, e):
        self.output_list.controls.clear()
        self._safe_page_update()

    def connect_or_resume(self, e):
        server_to_connect = self.server_dd.value
        if not server_to_connect:
            self.socket_manager._add_output("Please select a server to connect.", color=ft.Colors.RED)
            self._safe_page_update()
            return
        if not self.socket_manager.client_socket or not self.socket_manager.running:
            self.socket_manager.connect_to_server(server_to_connect)
        else:
            self.socket_manager.start_listening()
            self.socket_manager._add_output(f"Already connected/listening to {server_to_connect}.",
                                            color=ft.Colors.BLUE)
        self._safe_page_update()
        self.update_stop_button_state()

    def _safe_page_update(self):
        try:
            self.page.update()
        except Exception as e:
            print(f"Error updating page in TestController: {e}")


# --- main function (unchanged) ---
def main(page: ft.Page):
    page.window_height = 720
    page.window_width = 1080
    page.title = "Manual Draggable Divider Test Controller"
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE_GREY)
    page.dark_theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE_GREY)
    page.theme_mode = ft.ThemeMode.LIGHT

    controller = TestController(page)

    def on_window_event(e: ft.ControlEvent):
        if e.data == "close":
            print("Window close event triggered.")
            controller.socket_manager.stop()

    page.on_window_event = on_window_event
    page.update()


if __name__ == "__main__":
    ft.app(target=main)