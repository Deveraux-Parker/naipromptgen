import sys
import os
import json
import random
import logging
import zipfile
from io import BytesIO

import requests
from PIL import Image
from PyQt5.QtWidgets import (
    QApplication, QWidget, QMainWindow, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QLineEdit, QComboBox, QListWidget, QListWidgetItem, QMessageBox, QFileDialog,
    QScrollArea, QTextEdit, QProgressDialog, QDialog, QDialogButtonBox, QGridLayout, QSizePolicy,
    QCheckBox
)
from PyQt5.QtGui import QPixmap, QColor, QPalette, QFont, QIcon
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')


def load_json_data(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
            logging.debug(f"Loaded data from {file_path}")
            return data
    except Exception as e:
        logging.error(f"Failed to load JSON data from {file_path}: {e}")
        return {}


def extract_d_groups(tags):
    d_groups = set()
    for tag in tags:
        if 'd_group' in tag:
            d_groups.update(tag['d_group'])
    return sorted(d_groups)


def extract_artists(tags):
    artists = []
    for tag in tags:
        if tag['d_category'] == 'artist':
            power = max(tag.get('d_count', 0), tag.get('n_count', 0))
            artists.append((tag['tag_name'], power))
    return sorted(set(artists), key=lambda x: (-x[1], x[0]))


def search_tags(keyword, tags, category, d_group, artist, min_power, max_power):
    keyword = keyword.lower().strip()
    if category == "ALL":
        filtered_tags = tags
    else:
        filtered_tags = [tag for tag in tags if tag['d_category'] == category]
    if d_group != "ALL":
        filtered_tags = [tag for tag in filtered_tags if 'd_group' in tag and d_group in tag['d_group']]
    if artist != "ALL":
        artist_name = artist.split('[')[0].strip()
        filtered_tags = [tag for tag in filtered_tags if tag['tag_name'] == artist_name]

    # If keyword is not empty, filter by keyword
    if keyword:
        filtered_tags = [
            tag for tag in filtered_tags
            if keyword in tag['tag_name'].lower()
        ]

    # Finally, apply power filters
    return [
        {**tag, 'power': tag['d_count'] if tag.get('d_count', 0) > tag.get('n_count', 0) else tag.get('n_count', 0)}
        for tag in filtered_tags
        if min_power <= max(tag.get('d_count', 0), tag.get('n_count', 0)) <= max_power
    ]


class ImageGenerationThread(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, prompt, api_token, parent=None):
        super().__init__(parent)
        self.prompt = prompt
        self.api_token = api_token  # Receive API token as an argument

    def run(self):
        try:
            self.progress.emit("Starting image generation...")
            # Prepare the prompt
            keywords_to_remove = ['censor', 'censored', 'bar censor', 'mosaic censoring']
            prompt_words = self.prompt.split(', ')
            filtered_prompt_words = [word for word in prompt_words if word.lower() not in keywords_to_remove]
            filtered_prompt = ', '.join(filtered_prompt_words)

            logging.debug(f"Original prompt: {self.prompt}")
            logging.debug(f"Filtered prompt: {filtered_prompt}")

            # Generate the image
            image_data = self.generate_image(filtered_prompt, self.api_token)
            if not image_data:
                self.error.emit("Image generation failed.")
                return

            # Save and extract the image
            image_path = self.save_image(image_data)
            if not image_path:
                self.error.emit("Failed to save or extract the image.")
                return

            self.finished.emit(image_path)

        except Exception as e:
            logging.error(f"Unexpected error during image generation: {e}")
            self.error.emit(f"Unexpected error: {e}")

    def generate_image(self, prompt, api_key):
        url = "https://image.novelai.net/ai/generate-image"

        headers = {
            "Authorization": f"Bearer {api_key}"
        }

        payload = {
            "input": prompt,
            "model": "nai-diffusion-3",
            "action": "generate",
            "parameters": {
                "params_version": 3,
                "width": 832,
                "height": 1216,
                "scale": 7,
                "sampler": "k_dpmpp_2s_ancestral",
                "steps": 28,
                "n_samples": 1,
                "ucPreset": 3,
                "qualityToggle": False,
                "sm": False,
                "sm_dyn": False,
                "dynamic_thresholding": False,
                "controlnet_strength": 1,
                "legacy": False,
                "add_original_image": True,
                "cfg_rescale": 0,
                "noise_schedule": "karras",
                "legacy_v3_extend": False,
                "skip_cfg_above_sigma": None,
                "seed": random.randint(0, 4294967295),  # Random seed
                "negative_prompt": "worst quality, low quality, bad image, displeasing, [abstract], bad anatomy, very displeasing, extra, unfocused, jpeg artifacts, unfinished, chromatic aberration,"
            }
        }

        logging.debug(f"Sending request to NovelAI with prompt: '{prompt}'")
        try:
            response = requests.post(url, json=payload, headers=headers)
        except Exception as e:
            logging.error(f"Request to NovelAI failed: {e}")
            self.error.emit(f"Request to NovelAI failed: {e}")
            return None

        if response.status_code != 200:
            logging.error(f"Failed to generate image. Status code: {response.status_code}")
            logging.error(f"Response Headers: {response.headers}")
            logging.error(f"Response Body: {response.text}")
            self.error.emit(f"Failed to generate image. Status code: {response.status_code}")
            return None

        logging.debug("Image generated successfully.")
        return response.content

    def save_image(self, image_data, output_folder="images"):
        try:
            os.makedirs(output_folder, exist_ok=True)
            zip_path = os.path.join(output_folder, "output_image.zip")
            with open(zip_path, "wb") as f:
                f.write(image_data)
            logging.debug(f"Saved image zip as {zip_path}")

            # Extract the image from the zip file using BytesIO
            with zipfile.ZipFile(BytesIO(image_data), 'r') as zip_ref:
                zip_ref.extractall(output_folder)
            logging.debug(f"Extracted image to {output_folder}")

            extracted_image_path = os.path.join(output_folder, "image_0.png")
            if os.path.exists(extracted_image_path):
                logging.debug(f"Extracted image saved as {extracted_image_path}")
                # Rename the image to a unique name
                image_files = [f for f in os.listdir(output_folder) if f.startswith("image_") and f.endswith(".png")]
                image_numbers = [int(f.split("_")[1].split(".")[0]) for f in image_files if
                                 f.split("_")[1].split(".")[0].isdigit()]
                next_number = max(image_numbers, default=-1) + 1
                new_image_path = os.path.join(output_folder, f"image_{next_number}.png")
                os.rename(extracted_image_path, new_image_path)
                logging.debug(f"Renamed image to {new_image_path}")
                return new_image_path
            else:
                logging.warning("Could not find extracted image.")
                return None
        except Exception as e:
            logging.error(f"Failed to save or extract image: {e}")
            self.error.emit(f"Failed to save or extract image: {e}")
            return None


class GalleryWidget(QWidget):
    prompt_selected = pyqtSignal(str)  # Signal to emit the prompt when an image is clicked

    def __init__(self, generated_images, parent=None):
        super().__init__(parent)
        self.generated_images = generated_images  # dict mapping prompt to image_path
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        # Ensure vertical scrolling and disable horizontal scrolling
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(scroll)

        self.container = QWidget()
        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(10)  # Add spacing between thumbnails
        self.container.setLayout(self.grid_layout)
        scroll.setWidget(self.container)

        # Define number of columns (set to 2)
        self.columns = 2
        self.row = 0
        self.col = 0

        self.populate_gallery()

    def populate_gallery(self):
        for prompt, image_path in self.generated_images.items():
            if not os.path.exists(image_path):
                continue  # Skip if image file doesn't exist
            self.add_thumbnail(prompt, image_path)

    def add_thumbnail(self, prompt, image_path):
        thumb_button = QPushButton()
        thumb_button.setFixedSize(150, 150)
        thumb_button.setStyleSheet("border: none;")

        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return  # Skip if pixmap couldn't be loaded
        scaled_pixmap = pixmap.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        thumb_button.setIcon(QIcon(scaled_pixmap))
        thumb_button.setIconSize(QSize(150, 150))

        thumb_button.clicked.connect(lambda checked, p=prompt: self.prompt_selected.emit(p))

        self.grid_layout.addWidget(thumb_button, self.row, self.col)
        self.col += 1
        if self.col >= self.columns:
            self.col = 0
            self.row += 1

    def refresh_gallery(self, generated_images):
        # Clear existing thumbnails
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        # Reset row and column
        self.row = 0
        self.col = 0
        # Update generated_images
        self.generated_images = generated_images
        # Repopulate
        self.populate_gallery()

    def add_new_image(self, prompt, image_path):
        self.generated_images[prompt] = image_path
        self.add_thumbnail(prompt, image_path)


class CombinedApp(QMainWindow):
    def __init__(self, tags, artists, prompts):
        super().__init__()
        self.tags = tags
        self.artists = artists
        self.prompts = prompts
        self.generated_images_file = "generated_images.json"
        self.generated_images = self.load_generated_images()
        self.api_token = self.load_api_token()  # Load API token
        self.setWindowTitle("Combined Tag Search and Prompt Finder")
        self.setGeometry(100, 100, 1800, 900)
        self.setup_ui()

    def setup_ui(self):
        # Check and prompt for API token if necessary
        if not self.api_token:
            self.prompt_api_token()

        # Main widget and layout
        main_widget = QWidget()
        main_layout = QHBoxLayout()
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        # Tag Search Section
        tag_search_widget = TagSearchWidget(self.tags, self.artists, self.update_promptcheck)
        main_layout.addWidget(tag_search_widget, 2)

        # Separator
        separator = QLabel("|")
        separator.setAlignment(Qt.AlignCenter)
        separator.setStyleSheet("font-size: 24px;")
        main_layout.addWidget(separator)

        # Prompt Finder Section
        prompt_finder_widget = PromptFinderWidget(self.prompts, self.handle_prompt_click)
        main_layout.addWidget(prompt_finder_widget, 3)

        # Image Display and Gallery Section
        image_display_container = QWidget()
        image_display_layout = QVBoxLayout()
        image_display_container.setLayout(image_display_layout)
        main_layout.addWidget(image_display_container, 4)

        # Add toggle button for gallery
        toggle_gallery_button = QPushButton("Toggle Gallery")
        image_display_layout.addWidget(toggle_gallery_button)
        toggle_gallery_button.clicked.connect(self.toggle_gallery)

        # Image Display Widget
        self.image_display_widget = ImageDisplayWidget()
        image_display_layout.addWidget(self.image_display_widget)

        # Gallery Widget (initially hidden)
        self.gallery_widget = GalleryWidget(self.generated_images)
        self.gallery_widget.prompt_selected.connect(self.on_gallery_prompt_selected)
        self.gallery_widget.hide()
        image_display_layout.addWidget(self.gallery_widget)

        # Store references
        self.tag_search_widget = tag_search_widget
        self.prompt_finder_widget = prompt_finder_widget
        self.image_display_container = image_display_container

    def prompt_api_token(self):
        dialog = APIPromptDialog()
        if dialog.exec_() == QDialog.Accepted:
            entered_token, save_token = dialog.get_inputs()
            if entered_token:
                self.api_token = entered_token
                if save_token:
                    self.save_api_token(entered_token)
        else:
            # User cancelled the dialog; proceed without saving the token
            self.api_token = None

    def load_api_token(self):
        try:
            with open("apitoken.json", "r", encoding='utf-8') as f:
                data = json.load(f)
                token = data.get("token", "").strip()
                if token:
                    logging.debug("API token loaded successfully.")
                    return token
                else:
                    logging.debug("API token is empty.")
                    return None
        except FileNotFoundError:
            logging.debug("apitoken.json not found.")
            return None
        except Exception as e:
            logging.error(f"Failed to load API token: {e}")
            return None

    def save_api_token(self, token):
        try:
            with open("apitoken.json", "w", encoding='utf-8') as f:
                json.dump({"token": token}, f, indent=4)
            logging.debug("API token saved to apitoken.json")
        except Exception as e:
            logging.error(f"Failed to save API token: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save API token: {e}")

    def toggle_gallery(self):
        if self.gallery_widget.isVisible():
            self.gallery_widget.hide()
            self.image_display_widget.show()
        else:
            self.image_display_widget.hide()
            self.gallery_widget.show()

    def on_gallery_prompt_selected(self, prompt):
        logging.debug(f"Gallery prompt selected: {prompt}")
        self.prompt_finder_widget.set_prompt(prompt)

    def load_generated_images(self):
        if os.path.exists(self.generated_images_file):
            try:
                with open(self.generated_images_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logging.debug("Loaded generated_images.json")
                    return data
            except Exception as e:
                logging.error(f"Failed to load {self.generated_images_file}: {e}")
                return {}
        else:
            return {}

    def save_generated_images(self):
        try:
            with open(self.generated_images_file, 'w', encoding='utf-8') as f:
                json.dump(self.generated_images, f, indent=4)
            logging.debug("Saved generated_images.json")
        except Exception as e:
            logging.error(f"Failed to save {self.generated_images_file}: {e}")

    def update_promptcheck(self, tag):
        current_prompt = self.prompt_finder_widget.get_prompt_text()
        if current_prompt:
            # Avoid duplicating tags
            tags = [t.strip() for t in current_prompt.split(',')]
            if tag not in tags:
                new_prompt = f"{current_prompt}, {tag}"
            else:
                new_prompt = current_prompt
        else:
            new_prompt = tag
        logging.debug(f"Appending tag '{tag}' to prompt. New prompt: '{new_prompt}'")
        self.prompt_finder_widget.set_prompt(new_prompt)

    def handle_prompt_click(self, prompt, click_type):
        # We no longer need 'click_type' since we're handling everything with single-click
        # Modify the function signature accordingly if needed
        image_path = self.generated_images.get(prompt)
        if image_path and os.path.exists(image_path):
            logging.debug(f"Image exists for prompt: {prompt}, displaying {image_path}")
            self.image_display_widget.display_image(image_path)
        else:
            logging.debug(f"No image found for prompt: {prompt}")
            reply = QMessageBox.question(
                self,
                "Generate Image",
                "No image found for this prompt. Do you want to generate it?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                if not self.api_token:
                    # Prompt for API token before generating image
                    self.prompt_api_token()
                    if not self.api_token:
                        QMessageBox.warning(self, "API Token Required", "API token is required to generate images.")
                        return
                self.generate_image(prompt)

    def generate_image(self, prompt):
        # Start the image generation thread
        self.progress_dialog = QProgressDialog("Generating Image...", "Cancel", 0, 0, self)
        self.progress_dialog.setWindowTitle("Please Wait")
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.setCancelButton(None)
        self.progress_dialog.show()

        self.image_thread = ImageGenerationThread(prompt, self.api_token)  # Pass the API token
        self.image_thread.progress.connect(self.progress_dialog.setLabelText)
        self.image_thread.finished.connect(self.on_image_generated)
        self.image_thread.error.connect(self.on_image_error)
        self.image_thread.start()

    def on_image_generated(self, image_path):
        self.progress_dialog.close()
        # Update the mapping
        prompt = self.image_thread.prompt
        self.generated_images[prompt] = image_path
        self.save_generated_images()
        # Display the image
        self.image_display_widget.display_image(image_path)
        # Add the new image to the gallery
        self.gallery_widget.add_new_image(prompt, image_path)
        QMessageBox.information(self, "Success", f"Image generated and saved to {image_path}")

    def on_image_error(self, error_message):
        self.progress_dialog.close()
        QMessageBox.critical(self, "Error", error_message)


class TagSearchWidget(QWidget):
    def __init__(self, tags, artists, update_promptcheck_callback):
        super().__init__()
        self.tags = tags
        self.artists = artists
        self.update_promptcheck_callback = update_promptcheck_callback
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Search Bar Layout
        search_layout = QHBoxLayout()

        self.keyword_entry = QLineEdit()
        self.keyword_entry.setPlaceholderText("Enter keyword (optional)...")
        search_layout.addWidget(QLabel("Keyword:"))
        search_layout.addWidget(self.keyword_entry)

        self.category_combo = QComboBox()
        self.category_combo.addItems(["ALL", "general", "artist", "copyright", "character", "meta", "none"])
        search_layout.addWidget(QLabel("Category:"))
        search_layout.addWidget(self.category_combo)

        self.d_group_button = QPushButton("Select D-Group")
        search_layout.addWidget(self.d_group_button)

        self.artist_button = QPushButton("Select Artist")
        search_layout.addWidget(self.artist_button)

        self.min_power_entry = QLineEdit("0")
        self.min_power_entry.setFixedWidth(60)
        search_layout.addWidget(QLabel("Min Power:"))
        search_layout.addWidget(self.min_power_entry)

        self.max_power_entry = QLineEdit("10000")
        self.max_power_entry.setFixedWidth(60)
        search_layout.addWidget(QLabel("Max Power:"))
        search_layout.addWidget(self.max_power_entry)

        self.search_button = QPushButton("Search")
        search_layout.addWidget(self.search_button)

        layout.addLayout(search_layout)

        # Results List
        self.results_list = QListWidget()
        self.results_list.setSpacing(5)
        self.results_list.setStyleSheet("background-color: #2e2e2e; color: white;")
        layout.addWidget(self.results_list)

        # Connect signals
        self.search_button.clicked.connect(self.perform_search)
        self.d_group_button.clicked.connect(self.show_d_group_popup)
        self.artist_button.clicked.connect(self.show_artist_popup)
        self.keyword_entry.returnPressed.connect(self.perform_search)
        self.results_list.itemClicked.connect(self.on_item_clicked)  # Connect the signal to the handler

        # Initialize variables
        self.selected_d_group = "ALL"
        self.selected_artist = "ALL"

    def show_d_group_popup(self):
        d_group_options = ["ALL"] + extract_d_groups(self.tags)
        dialog = SelectionDialog("Select D-Group", d_group_options)
        if dialog.exec_() == QDialog.Accepted:
            self.selected_d_group = dialog.get_selected_item()
            self.perform_search()

    def show_artist_popup(self):
        artist_options = ["ALL"] + [f"{artist[0]} [{artist[1]}]" for artist in self.artists]
        dialog = SelectionDialog("Select Artist", artist_options)
        if dialog.exec_() == QDialog.Accepted:
            self.selected_artist = dialog.get_selected_item()
            self.perform_search()

    def perform_search(self):
        keyword = self.keyword_entry.text().strip()
        # Allow search if keyword is present or if d_group or artist is selected
        if not keyword and self.selected_d_group == "ALL" and self.selected_artist == "ALL":
            QMessageBox.warning(self, "Input Error", "Please enter a keyword or select a d-group or artist to search.")
            return

        category = self.category_combo.currentText()
        d_group = self.selected_d_group
        artist = self.selected_artist
        try:
            min_power = int(self.min_power_entry.text())
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Min Power must be an integer.")
            return
        try:
            max_power = int(self.max_power_entry.text())
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Max Power must be an integer.")
            return

        if min_power > max_power:
            QMessageBox.warning(self, "Input Error", "Min Power cannot be greater than Max Power.")
            return

        logging.debug(
            f"Performing search with keyword='{keyword}', category='{category}', d_group='{d_group}', artist='{artist}', min_power={min_power}, max_power={max_power}"
        )

        results = search_tags(keyword, self.tags, category, d_group, artist, min_power, max_power)
        self.display_results(results)

    def display_results(self, results):
        self.results_list.clear()
        if not results:
            self.results_list.addItem("No matching tags found.")
            return

        max_results = 1000  # Limit to prevent excessive memory usage
        limited_results = results[:max_results]
        for index, tag in enumerate(limited_results):
            # Create a custom widget for each item
            item_widget = PromptListItem(tag['tag_name'], tag['power'], tag['d_category'], index)
            list_item = QListWidgetItem(self.results_list)
            list_item.setSizeHint(item_widget.sizeHint())
            self.results_list.addItem(list_item)
            self.results_list.setItemWidget(list_item, item_widget)
        logging.debug(f"Displayed {len(limited_results)} results out of {len(results)} total matching tags.")

    def on_item_clicked(self, item):
        widget = self.results_list.itemWidget(item)
        if isinstance(widget, PromptListItem):
            tag_name = widget.tag_name
            logging.debug(f"Tag clicked: {tag_name}")
            self.update_promptcheck_callback(tag_name)


class PromptListItem(QWidget):
    def __init__(self, tag_name, power, category, index, parent=None):
        super().__init__(parent)
        self.tag_name = tag_name
        self.power = power
        self.category = category
        self.index = index
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Tag Name and Power
        tag_label = QLabel(f"{self.tag_name} - Power: {self.power}")
        tag_label.setWordWrap(True)
        tag_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(tag_label)

        # Set background color based on category and alternating for visual cue
        colors = {
            'general': '#00cc66',
            'artist': '#ffcc00',
            'copyright': '#33ccff',
            'character': '#ff6699',
            'meta': '#99cc00',
            'none': '#808080',
        }
        base_color = colors.get(self.category, '#ffffff')
        # Alternate brightness for visual cue
        if self.index % 2 == 0:
            bg_color = base_color
        else:
            bg_color = self.adjust_color_brightness(base_color, 0.9)
        self.setStyleSheet(f"background-color: {bg_color}; border-radius: 5px; padding: 5px;")

    def adjust_color_brightness(self, hex_color, factor=1.0):
        # Adjust the brightness of the color by a factor
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
        adjusted_rgb = tuple(min(int(c * factor), 255) for c in rgb)
        return '#{:02x}{:02x}{:02x}'.format(*adjusted_rgb)


class PromptFinderWidget(QWidget):
    def __init__(self, prompts, generate_image_callback):
        super().__init__()
        self.prompts = prompts
        self.generate_image_callback = generate_image_callback
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Search Input
        self.input_label = QLabel(
            "Enter keywords separated by commas. Click a prompt to display or generate its image.")
        self.input_label.setStyleSheet("color: white;")
        layout.addWidget(self.input_label)

        self.input_entry = QLineEdit()
        self.input_entry.setPlaceholderText("e.g., scenery, portrait")
        layout.addWidget(self.input_entry)

        # Connect signals
        self.input_entry.returnPressed.connect(self.search_prompts)

        # Search Button
        self.search_button = QPushButton("Search")
        layout.addWidget(self.search_button)
        self.search_button.clicked.connect(self.search_prompts)

        # Results List
        self.results_list = QListWidget()
        self.results_list.setSpacing(5)
        self.results_list.setStyleSheet("background-color: #2e2e2e; color: white;")
        layout.addWidget(self.results_list)

        # Connect item single-click
        self.results_list.itemClicked.connect(self.on_item_clicked)

    def set_prompt(self, prompt):
        self.input_entry.setText(prompt)
        self.search_prompts()

    def get_prompt_text(self):
        return self.input_entry.text().strip()

    def search_prompts(self):
        keywords = self.input_entry.text().split(',')
        keywords = [keyword.strip().lower() for keyword in keywords if keyword.strip()]
        logging.debug(f"Searching prompts with keywords: {keywords}")

        if not keywords and not self.input_entry.text().strip():
            # No keywords entered, display all prompts
            matching_prompts = self.prompts
        else:
            if not keywords:
                # If no keywords, match all prompts
                matching_prompts = self.prompts
            else:
                # Match prompts containing all keywords
                matching_prompts = [prompt for prompt in self.prompts if
                                    all(keyword in prompt.lower() for keyword in keywords)]

        self.results_list.clear()
        if matching_prompts:
            max_results = 1000  # Limit to prevent excessive memory usage
            selected_prompts = random.sample(matching_prompts, min(max_results, len(matching_prompts)))
            for prompt in selected_prompts:
                # Create a custom widget for each prompt
                item_widget = PromptDisplayItem(prompt)
                list_item = QListWidgetItem(self.results_list)
                list_item.setSizeHint(item_widget.sizeHint())
                self.results_list.addItem(list_item)
                self.results_list.setItemWidget(list_item, item_widget)
            logging.debug(f"Displayed {len(selected_prompts)} matching prompts out of {len(matching_prompts)} total.")
        else:
            self.results_list.addItem("No matching prompts found.")

    def on_item_clicked(self, item):
        prompt = self.get_prompt_from_item(item)
        if prompt:
            logging.debug(f"Prompt clicked: {prompt}")
            self.generate_image_callback(prompt, "single")

    def get_prompt_from_item(self, item):
        widget = self.results_list.itemWidget(item)
        if isinstance(widget, PromptDisplayItem):
            return widget.prompt_text
        return None


class PromptDisplayItem(QWidget):
    def __init__(self, prompt_text, parent=None):
        super().__init__(parent)
        self.prompt_text = prompt_text
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Prompt Text
        prompt_label = QLabel(self.prompt_text)
        prompt_label.setWordWrap(True)
        prompt_label.setStyleSheet("font-size: 14px;")
        layout.addWidget(prompt_label)

        # Add a subtle separator
        separator = QLabel("")
        separator.setFixedHeight(1)
        separator.setStyleSheet("background-color: #555555;")
        layout.addWidget(separator)


class ImageDisplayWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        self.image_label = QLabel("Generated Image will appear here.")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("color: white; font-size: 16px;")
        layout.addWidget(self.image_label)

    def display_image(self, image_path):
        try:
            logging.debug(f"Displaying image from {image_path}")
            pixmap = QPixmap(image_path)
            if pixmap.isNull():
                raise ValueError("Pixmap is null.")
            # Scale the image to fit the label while maintaining aspect ratio
            scaled_pixmap = pixmap.scaled(
                self.image_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.image_label.setPixmap(scaled_pixmap)
            self.image_label.setText("")  # Clear the placeholder text
            logging.debug(f"Image displayed from {image_path}")
        except Exception as e:
            logging.error(f"Failed to display image: {e}")
            QMessageBox.critical(self, "Error", f"Failed to display image: {e}")

    def resizeEvent(self, event):
        # Rescale the image when the widget is resized
        if self.image_label.pixmap():
            self.image_label.setPixmap(self.image_label.pixmap().scaled(
                self.image_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            ))


class SelectionDialog(QDialog):
    def __init__(self, title, options, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.selected_item = None
        self.init_ui(options)

    def init_ui(self, options):
        layout = QVBoxLayout()
        self.setLayout(layout)

        self.combo = QComboBox()
        self.combo.addItems(options)
        layout.addWidget(self.combo)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_selected_item(self):
        return self.combo.currentText()


class APIPromptDialog(QDialog):
    """
    Dialog to prompt the user for their API token and whether to save it.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Enter NovelAI API Token")
        self.init_ui()  # Corrected: Removed 'options' parameter

    def init_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Instruction Label
        instruction = QLabel("Please enter your NovelAI API token:")
        instruction.setWordWrap(True)
        layout.addWidget(instruction)

        # API Token Input
        self.api_input = QLineEdit()
        self.api_input.setEchoMode(QLineEdit.Password)
        self.api_input.setPlaceholderText("API Token")
        layout.addWidget(self.api_input)

        # Save Token Checkbox
        self.save_checkbox = QCheckBox("Save API token for future use")
        layout.addWidget(self.save_checkbox)

        # Dialog Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def validate(self):
        if not self.api_input.text().strip():
            QMessageBox.warning(self, "Input Error", "API token cannot be empty.")
            return
        self.accept()

    def get_inputs(self):
        return self.api_input.text().strip(), self.save_checkbox.isChecked()


def main():
    # Load data
    tags_data = load_json_data('naidv3_tags_pretty.json')
    tags = tags_data.get('tags', [])
    artists = extract_artists(tags)
    prompts_data = load_json_data('safebooru_clean.json')
    prompts = prompts_data if isinstance(prompts_data, list) else []

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Apply dark theme
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(28, 28, 28))
    palette.setColor(QPalette.WindowText, Qt.white)
    palette.setColor(QPalette.Base, QColor(46, 46, 46))
    palette.setColor(QPalette.AlternateBase, QColor(28, 28, 28))
    palette.setColor(QPalette.ToolTipBase, Qt.white)
    palette.setColor(QPalette.ToolTipText, Qt.white)
    palette.setColor(QPalette.Text, Qt.white)
    palette.setColor(QPalette.Button, QColor(28, 28, 28))
    palette.setColor(QPalette.ButtonText, Qt.white)
    palette.setColor(QPalette.BrightText, Qt.red)
    palette.setColor(QPalette.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.HighlightedText, Qt.black)
    app.setPalette(palette)

    window = CombinedApp(tags, artists, prompts)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

