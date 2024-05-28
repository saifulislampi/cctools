import json
import multiprocessing
import os
import signal
import sys
import threading
import time
from multiprocessing import Manager, Condition, Process
from config_loader import load_and_preprocess_config, validate_and_sort_programs
from program_executor import execute_program


def save_state_times(state_times, output_file):
    print(state_times)

    state_times_dict = dict(state_times)

    for key, value in state_times_dict.items():
        state_times_dict[key] = dict(value)

    with open(output_file, 'w') as f:
        json.dump(state_times_dict, f, indent=2)


class ServiceManager:
    def __init__(self, config_path):
        print("DEBUG: Initializing ServiceManager")
        self.config = load_and_preprocess_config(config_path)
        self.services = self.config['services']
        self.sorted_services = validate_and_sort_programs(self.config)
        self.working_dir = os.path.dirname(os.path.abspath(config_path))
        self.output = self.config['output']
        self.stop_signal_path = os.path.join(self.working_dir, self.config.get('stop_signal', ''))
        self.max_run_time = self.config.get('max_run_time', None)
        self.stop_event = multiprocessing.Event()
        self.pgid_dict = multiprocessing.Manager().dict()
        self.state_dict = multiprocessing.Manager().dict()
        self.state_times = multiprocessing.Manager().dict()
        self.cond = multiprocessing.Condition()
        self.processes = {}
        print("DEBUG: ServiceManager initialized")

    def setup_signal_handlers(self):
        print("DEBUG: Setting up signal handlers")
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)

    def signal_handler(self, signum, frame):
        print(f"DEBUG: Received signal {signum} in pid {os.getpid()}, stopping all services...")
        self.stop_event.set()

    def start_services(self, start_time):
        print("DEBUG: Starting services")
        self.setup_signal_handlers()

        for service in self.sorted_services:
            service_config = self.services[service]

            self.state_dict[service] = "initial"
            self.state_times[service] = {}

            p_exec = Process(target=execute_program, args=(
                service_config, self.working_dir, self.state_dict, service, self.cond, self.state_times, start_time,
                self.pgid_dict, self.stop_event))

            p_exec.start()
            self.processes[service] = p_exec

        print("DEBUG: All services initialized")

        stop_thread = threading.Thread(target=self.check_stop_conditions, args=(start_time,))
        stop_thread.start()

        for p in self.processes.values():
            p.join()

        stop_thread.join()

        if os.path.exists(self.stop_signal_path):
            os.remove(self.stop_signal_path)

        save_state_times(self.state_times, os.path.join(self.working_dir, self.output['state_times']))

    def check_stop_conditions(self, start_time):
        print("DEBUG: Checking stop conditions")
        while not self.stop_event.is_set():
            if self.check_stop_signal_file() or self.check_max_run_time(start_time):
                self.stop_event.set()
            else:
                self.stop_event.wait(timeout=1)

        self.stop_all_services()

        print("DEBUG: Finished checking stop conditions")

    def stop_all_services(self):
        print("DEBUG: Stopping all services")
        for service_name, process in self.processes.items():
            pgid = self.pgid_dict.get(service_name)
            if pgid:
                try:
                    os.killpg(pgid, signal.SIGTERM)
                except ProcessLookupError:
                    print(f"Process group {pgid} for service {service_name} not found.")
            process.terminate()

        for process in self.processes.values():
            process.join()

        print("DEBUG: All services have been stopped")

    def stop_service(self, service_name):
        if service_name in self.processes:
            process = self.processes[service_name]
            if process.is_alive():
                pgid = self.pgid_dict.get(service_name)
                if pgid:
                    os.killpg(pgid, signal.SIGTERM)  # Terminate the process group

                process.terminate()
                process.join()
            print(f"Service {service_name} has been stopped.")
        else:
            print(f"Service {service_name} not found.")

    def check_stop_signal_file(self):
        if os.path.exists(self.stop_signal_path):
            print("Received stop signal")
            return True

    def check_max_run_time(self, start_time):
        if self.max_run_time:
            current_time = time.time()
            if (current_time - start_time) > self.max_run_time:
                print("Maximum runtime exceeded. Stopping all services.")
                return True
        return False
