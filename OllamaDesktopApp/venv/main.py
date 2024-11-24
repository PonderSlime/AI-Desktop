import sys
import os
from idlelib.iomenu import encoding

from pydub import AudioSegment
from pydub.playback import play
import tempfile
from pyexpat.errors import messages
from random import sample
from sys import audit

import ollama
from piper.voice import PiperVoice

import numpy as np
import sounddevice as sd
from PyQt5.QtCore import Qt, QThread, pyqtSignal, pyqtProperty, QSize
from PyQt5.QtGui import QColor, QPainter, QPen, QBrush
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLineEdit,
    QPushButton, QPlainTextEdit, QLabel, QScrollArea, QTabWidget,
    QHBoxLayout, QMessageBox, QSizePolicy, QFileDialog, QListWidget, QListWidgetItem, QToolButton, QMenu, QAction
)
import re
class WorkerThread(QThread):

    result_ready = pyqtSignal(str)
    chat_msg_history = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, model_txt, chat_messages, query, parent=None, ):
        super().__init__(parent)
        self.system_prompt = model_txt
        self.chat_messages = chat_messages
        self.query = query
        print(self.system_prompt)

    def create_message(self, message, role):
        return {
            'role': role,
            'content': message
        },

    def clean_response(self, response):
        cleaned_response = re.sub(r"<\|start_header_id\|>.*?<\|end_header_id\|>", "", response)
        return cleaned_response.strip()

    def chat(self):
        self.chat_messages = [msg[0] if isinstance(msg, tuple) else msg for msg in self.chat_messages]
        if not any(msg.get('role') == 'system' for msg in self.chat_messages):
            print("no system, creating a new one!")
            self.chat_messages.append(self.create_message(self.system_prompt, 'system'))

        self.chat_messages = [msg[0] if isinstance(msg, tuple) else msg for msg in self.chat_messages]
        if any(msg.get('role') == 'system' for msg in self.chat_messages):
            print("systtem alrready exists!")
        ollama_response = ollama.chat(model='llama3.2:1b', stream=True, messages=self.chat_messages)

        assistant_message = ''

        for chunk in ollama_response:
            assistant_message += chunk['message']['content']
            print(chunk['message']['content'], end='', flush=True)

        cleaned_message = self.clean_response(assistant_message)
        self.result_ready.emit(cleaned_message)
        self.chat_messages.append(self.create_message(cleaned_message, 'assistant'))
        self.chat_msg_history.emit(self.chat_messages)

    def run(self):
        self.chat_messages.append(
            self.create_message(self.query, 'user')
        )
        print(f'\n\n--{self.query}--\n\n')
        self.chat()
class TTSWorker(QThread):

    def __init__(self, input, parent=None):
        super().__init__(parent)
        self.text = input

    def get_resource_path(self, relative_path):
        """Get the absolute path to a resource, works for dev and PyInstaller."""
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_path, relative_path)

    def run(self):
        temp_file_path = None
        try:
            model = self.get_resource_path("src/lessac/en_US-lessac-medium.onnx")
            print(f"Looking for ONNX model at: {model}")

            voice = PiperVoice.load(model)

            # Create an empty AudioSegment to accumulate audio chunks
            audio_segment = AudioSegment.empty()

            # Generate audio and add chunks to the AudioSegment
            for audio_bytes in voice.synthesize_stream_raw(self.text):
                int_data = np.frombuffer(audio_bytes, dtype=np.int16)
                segment = AudioSegment(
                    int_data.tobytes(),
                    frame_rate=voice.config.sample_rate,
                    sample_width=2,  # int16 = 2 bytes
                    channels=1
                )
                audio_segment += segment

            # Save the audio as a temporary MP3 file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            temp_file_path = temp_file.name
            audio_segment.export(temp_file_path, format="mp3")
            temp_file.close()

            # Play the MP3 file
            play(AudioSegment.from_file(temp_file_path))

        except Exception as e:
            #self.tts_error.emit(f"TTS Error: {str(e)}")
            print(f"TTS Error: {str(e)}")
        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                os.remove(temp_file_path)

class FileItemWidget(QWidget):
    def __init__(self, file_name, remove_callback):
        super().__init__()
        self.file_name = file_name.replace(".txt","")
        self.remove_callback = remove_callback

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5,5,5,5)
        layout.setSpacing(10)

        self.file_label = QLabel(file_name)
        layout.addWidget(self.file_label)

        self.remove_button = QPushButton("❌")
        self.remove_button.setFixedSize(40,30)
        self.remove_button.clicked.connect(self.remove_item)
        layout.addWidget(self.remove_button)
        self.setMinimumHeight(60)


    def remove_item(self):
        self.remove_callback(self.file_name)

class FileWidget(QListWidgetItem):
    def __init__(self, file_name, file_path):
        super().__init__()  # Display the file name in the list
        self.return_name = file_path  # Store the full file path

class FadingCircle(QWidget):
    def  __init__(self):
        super().__init__()
        self.setFixedSize(100,100)
        self.current_color = QColor(0,0,255)

        self.color_animation = QPropertyAnimation(self, b"color")
        self.color_animation.setDuration(5000)
        self.color_animation.setStartValue(QColor(0, 0, 255))
        self.color_animation.setEndValue(QColor(255, 0, 0))
        self.color_animation.setEasingCurve(QEasingCurve.SineCurve)
        self.color_animation.setLoopCount(-1)
        self.color_animation.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        pen = QPen(self.current_color)
        pen.setWidth(4)
        painter.setPen(pen)
        painter.setBrush(QBrush(self.current_color))

        painter.translate(self.width() / 2, self.height() / 2)

        painter.drawEllipse(-20,-20,40,40)

        painter.end()

    def setColor(self, color):
        self.current_color = QColor(color)
        self.update()

    color = pyqtProperty(QColor, fget=lambda self: self.current_color, fset=setColor)

class OllamaApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ollama Desktop App")

        self.central_widget = QWidget()
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(15)

        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)

        self.tab_widget.tabCloseRequested.connect(self.close_tab)

        self.layout.addWidget(self.tab_widget)

        self.dropdown_button = QPushButton("Open Tab")

        self.dropdown_menu = QMenu()
        action_new_chat = QAction("New Chat", self)
        action_new_chat.triggered.connect(self.setup_chat_tab)
        self.dropdown_menu.addAction(action_new_chat)
        self.dropdown_button.setMenu(self.dropdown_menu)

        action_new_model_editor = QAction("Model Editor", self)
        action_new_model_editor.triggered.connect(self.setup_model_tab)
        self.dropdown_menu.addAction(action_new_model_editor)

        toolbar_layout = QHBoxLayout()
        toolbar_layout.addWidget(self.dropdown_button)
        toolbar_layout.addStretch()

        self.layout.addLayout(toolbar_layout)
        self.central_widget.setLayout(self.layout)
        self.setCentralWidget(self.central_widget)

        self.chat_tabs = {}  # Store chat tab layouts
        self.setup_chat_tab()
        self.setup_model_tab()

    def close_tab(self, index):
        """Handle tab close button click."""
        self.tab_widget.removeTab(index)
    def setup_chat_tab(self):
        # Default Chat Tab
        self.create_chat_tab("llama3.2:1b", "you are a friendly assistant")

    def setup_model_tab(self):
        # Model Editor Tab
        self.model_editor_tab = QWidget()
        self.setup_model_editor_tab()
        self.tab_widget.addTab(self.model_editor_tab, "Model Editor")

    def create_chat_tab(self, model_name, model_txt, tab_label=None):
        self.chat_messages = []

        if tab_label is None:
            tab_label = model_name

        new_chat_tab = QWidget()
        new_chat_layout = QVBoxLayout(new_chat_tab)

        # Scrollable output area for the chat
        output_area = QScrollArea()
        output_area.setWidgetResizable(True)
        messages_container = QWidget()
        messages_layout = QVBoxLayout(messages_container)
        messages_layout.setAlignment(Qt.AlignTop)
        messages_container.setLayout(messages_layout)
        output_area.setWidget(messages_container)
        new_chat_layout.addWidget(output_area)

        # Toolbar for input
        toolbar = QHBoxLayout()
        input_field = QLineEdit()
        input_field.setPlaceholderText(f"Chat with model: {model_name}...")
        toolbar.addWidget(input_field)

        submit_button = QPushButton("Submit")
        submit_button.clicked.connect(
            lambda: self.submit_query(model_txt, input_field, messages_layout)
        )
        toolbar.addWidget(submit_button)
        new_chat_layout.addLayout(toolbar)

        new_chat_tab.setLayout(new_chat_layout)
        self.tab_widget.addTab(new_chat_tab, tab_label)
        self.chat_tabs[tab_label] = {"layout": messages_layout, "model_name": model_name}

    def submit_query(self, model_txt, input_field, messages_layout):
        query = input_field.text().strip()
        if query:
            input_field.clear()
            self.worker_thread = WorkerThread(model_txt, self.chat_messages, query, self)
            self.add_message(query, True, messages_layout)

            self.worker_thread.result_ready.connect(
                lambda response: self.handle_response(response, messages_layout)
            )
            self.worker_thread.chat_msg_history.connect(
                lambda chat_messages: self.update_chat_msgs
            )
            self.worker_thread.error_occurred.connect(
                lambda error: self.handle_response(f"Error: {error}", False, messages_layout)
            )
            self.worker_thread.start()


    def update_chat_msgs(self, chat_messages):
        self.chat_messages = chat_messages

    def handle_response(self, response, messages_layout):
        # Add the message to the chat
        self.add_message(response, False, messages_layout)
        # Play the response using TTS
        self.play_tts(response)

    def add_message(self, message, is_user, layout):
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        if is_user:
            message_label.setStyleSheet("""
                background-color: #e6e6e6;
                color: #333;
                padding: 10px;
                margin: 5px;
                border-radius: 10px;
            """)
        else:
            message_label.setStyleSheet("""
                background-color: #cce5ff;
                color: #333;
                padding: 10px;
                margin: 5px;
                border-radius: 10px;
            """)

        container_layout = QHBoxLayout()
        if is_user:
            container_layout.addStretch()
            container_layout.addWidget(message_label)
        else:
            container_layout.addWidget(message_label)
            container_layout.addStretch()

        container_widget = QWidget()
        container_widget.setLayout(container_layout)
        layout.addWidget(container_widget)

    def play_tts(self, text):
        self.tts_worker = TTSWorker(text, self)
        self.tts_worker.start()

    def setup_model_editor_tab(self):
        self.model_editor_layout = QHBoxLayout()
        self.model_list = QListWidget()
        self.model_list.setFixedWidth(200)
        self.model_list.itemClicked.connect(self.load_selected_model)
        self.model_editor_layout.addWidget(self.model_list)

        editor_area = QVBoxLayout()
        self.model_name_field = QLineEdit()
        self.model_name_field.setPlaceholderText("Enter model name...")
        editor_area.addWidget(self.model_name_field)

        self.text_editor = QPlainTextEdit()
        self.text_editor.setPlaceholderText("Write your model here...")
        default_text = self.load_default_template("model_template.txt")
        self.text_editor.setPlainText(default_text)
        editor_area.addWidget(self.text_editor)

        save_button = QPushButton("Save Model")
        save_button.clicked.connect(self.save_model)
        editor_area.addWidget(save_button)

        run_button = QPushButton("Run with Model")
        run_button.clicked.connect(self.run_with_model)
        editor_area.addWidget(run_button)

        self.model_editor_layout.addLayout(editor_area)
        self.model_editor_tab.setLayout(self.model_editor_layout)

        self.refresh_model_list()

    def refresh_model_list(self):
        self.model_list.clear()

        models_dir = os.path.join(os.getcwd(), "models")
        trash_dir = os.path.join(os.getcwd(), "trash_models")
        os.makedirs(models_dir, exist_ok=True)
        os.makedirs(trash_dir, exist_ok=True)

        for filename in os.listdir(models_dir):
            if filename.endswith(".txt"):
                file_path = os.path.join(models_dir, filename)


                item = FileWidget(filename, file_path)
                item_widget = FileItemWidget(filename, self.move_to_trash)
                item.setSizeHint(QSize(0, 40))
                self.model_list.addItem(item)
                self.model_list.setItemWidget(item, item_widget)

    def save_model(self):
        model_name = self.model_name_field.text().strip()
        if not model_name:
            QMessageBox.warning(self, "Error", "Please enter a model name!")
            return

        text_content = self.text_editor.toPlainText().strip()
        if not text_content:
            QMessageBox.warning(self, "Error", "Model content cannot be empty!")
            return

        os.makedirs("models", exist_ok=True)
        model_path = os.path.join("models", f"{model_name}.txt")
        with open(model_path, "w", encoding="utf-8") as file:
            file.write(text_content)
        QMessageBox.information(self, "Success", f"Model saved to {model_path}")
        self.refresh_model_list()

    def run_with_model(self):
        model_name = self.model_name_field.text().strip()
        model_path = os.path.join("models", f"{model_name}.txt")
        if not model_name:
            QMessageBox.warning(self, "Error", "Please enter a model name!")
            return
        self.create_chat_tab(model_name, self.load_default_template(model_path), f"Chat with {model_name}")
        self.refresh_model_list()

    def load_selected_model(self, item):
        if isinstance(item, FileWidget):
            model_path = item.return_name

            if not os.path.isfile(model_path):
                QMessageBox.warning(self, "Error", f"Selected model '{model_path}' does not exist!")
                return
            try:
                with open(model_path, "r", encoding="utf-8") as file:
                    content = file.read()
                    self.text_editor.setPlainText(content)

                model_name = os.path.basename(model_path).replace(".txt","")
                self.model_name_field.setText(model_name)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load model: {str(e)}")
        else:
            # Handle cases where the item isn't a FileItemWidget
            QMessageBox.warning(self, "Error", "Invalid item selected!")

    def move_to_trash(self, file_name):
        models_dir = os.path.join(os.getcwd(), "models")
        trash_dir = os.path.join(os.getcwd(), "trash_models")

        os.makedirs(trash_dir, exist_ok=True)
        source_path = os.path.join(models_dir, file_name)
        destination_path = os.path.join(trash_dir, file_name)

        try:
            if os.path.exists(source_path):
                os.rename(source_path, destination_path)
                QMessageBox.information(self, "Removed", f"'{file_name}' moved to trash.")
                self.refresh_model_list()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not move '{file_name}' to trash.\n{str(e)}")

    def load_default_template(self, template_file):
        if os.path.exists(template_file):
            with open(template_file, "r", encoding="utf-8") as file:
                return file.read()
        return ""

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet("""
        QMainWindow {
            background-color: #f5f5f5;
        }
        QLineEdit {
            background-color: #ffffff;
            border: 1px solid #ccc;
            border-radius: 8px;
            padding: 8px;
            font-size: 14px;
        }
        QPushButton {
            background-color: #0078d7;
            color:white;
            border: none;
            border-radius: 8px;
            padding: 10px 15px;
            font-size: 14px;
        }
        QPushButton::hover {
            background-color: #005a9e;
        }
        QTextEdit {
            background-color: #ffffff;
            border: 1px solid #ccc;
            border-radius: 8px;
            padding: 8px;
            font-size: 14;
        }
        QLabel {
            font-size: 16px;
            font-weight: bold;
            color: #333;
        }
        div {}
    """)

    window = OllamaApp()
    window.show()
    sys.exit(app.exec_())