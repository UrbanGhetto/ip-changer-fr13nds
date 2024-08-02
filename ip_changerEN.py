import os
os.environ['PYQT_MAC_WANTS_SECURE_RESTORABLE_STATE'] = '1'

import sys
import requests
import random
import time
import webbrowser
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QComboBox, QLabel, QTextEdit, QProgressBar, QSystemTrayIcon, QMenu, QAction
from PyQt5.QtCore import QTimer, QThread, pyqtSignal, QEvent, Qt
from PyQt5.QtGui import QIcon
from concurrent.futures import ThreadPoolExecutor
import subprocess
import platform

class IPChecker(QThread):
    ip_checked = pyqtSignal(str)

    def run(self):
        try:
            response = requests.get('https://api.ipify.org', timeout=10)
            self.ip_checked.emit(response.text.strip())
        except Exception as e:
            self.ip_checked.emit(f"Failed to get IP: {str(e)}")

class ProxyChecker(QThread):
    finished = pyqtSignal(list)
    progress = pyqtSignal(int)

    def __init__(self, proxy_list, max_proxies=200):
        super().__init__()
        self.proxy_list = proxy_list[:max_proxies]
        self.max_proxies = max_proxies

    def run(self):
        working_proxies = []
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(self.check_proxy, proxy) for proxy in self.proxy_list]
            for i, future in enumerate(futures):
                result = future.result()
                if result:
                    working_proxies.append(result)
                self.progress.emit(int((i + 1) / len(self.proxy_list) * 100))
        self.finished.emit(working_proxies)

    def check_proxy(self, proxy):
        proxies = {
            'http': f'http://{proxy}',
            'https': f'http://{proxy}'
        }
        try:
            response = requests.get('https://api.ipify.org', proxies=proxies, timeout=5)
            return proxy if response.status_code == 200 else None
        except:
            return None

def set_proxy(proxy):
    host, port = proxy.split(':')
    system = platform.system()
    
    if system == "Darwin":  # macOS
        try:
            subprocess.run(['networksetup', '-setwebproxy', 'Wi-Fi', host, port], check=True)
            subprocess.run(['networksetup', '-setsecurewebproxy', 'Wi-Fi', host, port], check=True)
            return True
        except subprocess.CalledProcessError:
            return False
    elif system == "Windows":
        try:
            import winreg
            internet_settings = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r'Software\Microsoft\Windows\CurrentVersion\Internet Settings',
                0, winreg.KEY_ALL_ACCESS)
            winreg.SetValueEx(internet_settings, 'ProxyEnable', 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(internet_settings, 'ProxyServer', 0, winreg.REG_SZ, f"{host}:{port}")
            winreg.CloseKey(internet_settings)
            return True
        except Exception:
            return False
    elif system == "Linux":
        try:
            # Try GNOME
            subprocess.run(['gsettings', 'set', 'org.gnome.system.proxy', 'mode', 'manual'], check=True)
            subprocess.run(['gsettings', 'set', 'org.gnome.system.proxy.http', 'host', host], check=True)
            subprocess.run(['gsettings', 'set', 'org.gnome.system.proxy.http', 'port', port], check=True)
            return True
        except subprocess.CalledProcessError:
            try:
                # Try KDE
                subprocess.run(['kwriteconfig5', '--file', 'kioslaverc', '--group', 'Proxy Settings', '--key', 'ProxyType', '1'], check=True)
                subprocess.run(['kwriteconfig5', '--file', 'kioslaverc', '--group', 'Proxy Settings', '--key', 'httpProxy', f"{host} {port}"], check=True)
                return True
            except subprocess.CalledProcessError:
                return False
    else:
        return False

def disable_proxy():
    system = platform.system()
    
    if system == "Darwin":  # macOS
        try:
            subprocess.run(['networksetup', '-setwebproxystate', 'Wi-Fi', 'off'], check=True)
            subprocess.run(['networksetup', '-setsecurewebproxystate', 'Wi-Fi', 'off'], check=True)
            return True
        except subprocess.CalledProcessError:
            return False
    elif system == "Windows":
        try:
            import winreg
            internet_settings = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r'Software\Microsoft\Windows\CurrentVersion\Internet Settings',
                0, winreg.KEY_ALL_ACCESS)
            winreg.SetValueEx(internet_settings, 'ProxyEnable', 0, winreg.REG_DWORD, 0)
            winreg.CloseKey(internet_settings)
            return True
        except Exception:
            return False
    elif system == "Linux":
        try:
            # Try GNOME
            subprocess.run(['gsettings', 'set', 'org.gnome.system.proxy', 'mode', 'none'], check=True)
            return True
        except subprocess.CalledProcessError:
            try:
                # Try KDE
                subprocess.run(['kwriteconfig5', '--file', 'kioslaverc', '--group', 'Proxy Settings', '--key', 'ProxyType', '0'], check=True)
                return True
            except subprocess.CalledProcessError:
                return False
    else:
        return False

class IPChangerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_ip = "Checking IP..."
        self.original_ip = None
        self.proxy_list = []
        self.working_proxies = []
        self.initUI()
        self.initSystemTray()
        self.check_current_ip()

    def initUI(self):
        self.setWindowTitle('IP Changer')
        self.setGeometry(100, 100, 300, 400)

        layout = QVBoxLayout()

        self.ip_label = QLabel(f"Current IP: {self.current_ip}", self)
        layout.addWidget(self.ip_label)

        self.checkIPButton = QPushButton("Check IP on Web", self)
        self.checkIPButton.clicked.connect(self.check_ip_web)
        layout.addWidget(self.checkIPButton)

        self.changeIPOnceButton = QPushButton("Change IP Once", self)
        self.changeIPOnceButton.clicked.connect(self.change_ip_once)
        layout.addWidget(self.changeIPOnceButton)

        self.label = QLabel("Select Interval", self)
        layout.addWidget(self.label)

        self.combo = QComboBox(self)
        self.combo.addItems(["5 seconds", "10 seconds", "1 minute", "5 minutes", "10 minutes"])
        layout.addWidget(self.combo)

        self.startButton = QPushButton("Start Automatic IP Change", self)
        self.startButton.clicked.connect(self.start_changing_ip)
        layout.addWidget(self.startButton)

        self.stopButton = QPushButton("Stop", self)
        self.stopButton.clicked.connect(self.stop_changing_ip)
        layout.addWidget(self.stopButton)

        self.updateProxyButton = QPushButton("Update Proxy List", self)
        self.updateProxyButton.clicked.connect(self.update_proxy_list)
        layout.addWidget(self.updateProxyButton)

        self.resetButton = QPushButton("Reset IP", self)
        self.resetButton.clicked.connect(self.reset_ip)
        layout.addWidget(self.resetButton)

        self.progressBar = QProgressBar(self)
        self.progressBar.setVisible(False)
        layout.addWidget(self.progressBar)

        self.log = QTextEdit(self)
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

        central_widget = QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        self.timer = QTimer()
        self.timer.timeout.connect(self.change_ip)

    def initSystemTray(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon("path/to/your/icon.png"))  # Replace with your icon path

        tray_menu = QMenu()
        show_action = QAction("Show", self)
        quit_action = QAction("Quit", self)
        show_action.triggered.connect(self.show)
        quit_action.triggered.connect(self.quitApplication)
        tray_menu.addAction(show_action)
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray_icon.showMessage(
            "IP Changer",
            "Application is still running in the background.",
            QSystemTrayIcon.Information,
            2000
        )

    def quitApplication(self):
        self.tray_icon.hide()
        QApplication.quit()

    def update_proxy_list(self):
        self.log.append("Updating proxy list...")
        try:
            response = requests.get('https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all', timeout=15)
            self.proxy_list = response.text.split()
            self.log.append(f"Successfully updated proxy list. Total proxies: {len(self.proxy_list)}")
            self.check_proxies()
        except Exception as e:
            self.log.append(f"Failed to update proxy list: {str(e)}")
            self.log.append("Trying alternative proxy source...")
            try:
                response = requests.get('https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt', timeout=15)
                self.proxy_list = response.text.split()
                self.log.append(f"Successfully updated proxy list from alternative source. Total proxies: {len(self.proxy_list)}")
                self.check_proxies()
            except Exception as e:
                self.log.append(f"Failed to update proxy list from alternative source: {str(e)}")

    def check_proxies(self):
        self.log.append("Checking working proxies...")
        self.progressBar.setVisible(True)
        self.progressBar.setValue(0)
        self.proxy_checker = ProxyChecker(self.proxy_list)
        self.proxy_checker.finished.connect(self.on_proxy_check_finished)
        self.proxy_checker.progress.connect(self.update_progress)
        self.proxy_checker.start()

    def update_progress(self, value):
        self.progressBar.setValue(value)

    def on_proxy_check_finished(self, working_proxies):
        self.working_proxies = working_proxies
        self.log.append(f"Total working proxies: {len(self.working_proxies)}")
        self.progressBar.setVisible(False)

    def set_system_proxy(self, proxy):
        if set_proxy(proxy):
            self.log.append(f"System proxy successfully set to: {proxy}")
        else:
            self.log.append("Failed to set system proxy. Make sure you have sufficient access rights.")

    def disable_system_proxy(self):
        if disable_proxy():
            self.log.append("System proxy successfully disabled")
        else:
            self.log.append("Failed to disable system proxy. Make sure you have sufficient access rights.")

    def reset_ip(self):
        self.log.append("Resetting IP to original state...")
        self.disable_system_proxy()
        time.sleep(2)  # Give the system time to apply changes
        new_ip = self.get_current_ip()
        self.current_ip = new_ip
        self.ip_label.setText(f"Current IP: {self.current_ip}")
        if new_ip == self.original_ip:
            self.log.append(f"IP successfully reset to original IP: {self.current_ip}")
        else:
            self.log.append(f"IP has been reset, but differs from the original IP. Current IP: {self.current_ip}")
        self.log.append("Please check your IP in the browser to confirm the change.")

    def check_ip_web(self):
        webbrowser.open('https://whatismyipaddress.com/')
        self.log.append("Opening browser to check IP...")

    def change_ip_once(self):
        if not self.working_proxies:
            self.log.append("Working proxy list is empty. Please update the proxy list first.")
            return

        self.log.append("Attempting to change IP once...")
        self.change_ip()
        self.log.append("One-time IP change process completed.")

    def change_ip(self):
        if not self.working_proxies:
            self.log.append("Working proxy list is empty. Please update the proxy list first.")
            return

        max_attempts = 10
        for attempt in range(max_attempts):
            proxy = random.choice(self.working_proxies)
            try:
                self.set_system_proxy(proxy)
                time.sleep(2)
                new_ip = self.get_current_ip()
                if new_ip != self.current_ip:
                    self.current_ip = new_ip
                    self.ip_label.setText(f"Current IP: {self.current_ip}")
                    self.log.append(f"IP successfully changed to: {self.current_ip}")
                    self.log.append("System proxy has been set. Please check your IP in the browser.")
                    break
                else:
                    self.log.append(f"Attempt {attempt+1}: IP did not change. Trying another proxy...")
            except Exception as e:
                self.log.append(f"Attempt {attempt+1}: Failed to use proxy {proxy}: {str(e)}")
                self.working_proxies.remove(proxy)
                self.disable_system_proxy()
            
            if attempt == max_attempts - 1:
                self.log.append("Failed to change IP after several attempts.")

    def get_current_ip(self):
        try:
            response = requests.get('https://api.ipify.org', timeout=10)
            return response.text.strip()
        except Exception as e:
            return f"Failed to get IP: {str(e)}"

    def check_current_ip(self):
        self.current_ip = self.get_current_ip()
        self.ip_label.setText(f"Current IP: {self.current_ip}")
        if not self.original_ip:
            self.original_ip = self.current_ip

    def start_changing_ip(self):
        if not self.working_proxies:
            self.log.append("Working proxy list is empty. Please update the proxy list first.")
            return

        interval_str = self.combo.currentText()
        intervals = {
            "5 seconds": 5000,
            "10 seconds": 10000,
            "1 minute": 60000,
            "5 minutes": 300000,
            "10 minutes": 600000,
        }
        interval = intervals[interval_str]
        self.timer.start(interval)
        self.log.append(f"Started changing IP every {interval_str}")

    def stop_changing_ip(self):
        self.timer.stop()
        self.disable_system_proxy()
        self.log.append("Stopped changing IP and disabled system proxy")

class CustomApplication(QApplication):
    def __init__(self, argv):
        super().__init__(argv)

    def event(self, event):
        if event.type() == QEvent.ApplicationStateChange:
            if self.applicationState() == Qt.ApplicationActive:
                print("Application is active")
            elif self.applicationState() == Qt.ApplicationInactive:
                print("Application is inactive")
        return super().event(event)

    def applicationSupportsSecureRestorableState(self):
        return True

if __name__ == '__main__':
    app = CustomApplication(sys.argv)
    app.setApplicationName("IP Changer")
    app.setOrganizationName("YourOrganization")
    app.setOrganizationDomain("yourorganization.com")
    
    ex = IPChangerApp()
    ex.show()
    sys.exit(app.exec_())