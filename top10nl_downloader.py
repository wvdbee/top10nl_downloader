from . import resources
"""
Top10NL Downloader - A QGIS plugin for downloading Top10NL objects via OGC-API Features
"""

import os
import datetime
import configparser
# nieuw
import json
import urllib.request
import urllib.error
from qgis.PyQt.QtCore import Qt, QSettings, QTranslator, QCoreApplication, QVariant, QThread, pyqtSignal
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (QAction, QFileDialog, QMessageBox, 
                                QDialog, QVBoxLayout, QHBoxLayout, 
                                QLabel, QLineEdit, QTextEdit, QPushButton, 
                                QProgressBar, QRadioButton, QCheckBox, QGroupBox,
                                QListWidget, QListWidgetItem)
from qgis.core import (QgsProject, QgsRectangle, QgsVectorLayer, QgsLayerTreeGroup, QgsLayerTreeLayer,
                      QgsCoordinateReferenceSystem, QgsDataSourceUri, 
                      QgsProcessingFeedback, QgsTask, QgsApplication, 
                      QgsMessageLog, Qgis)
from qgis.gui import QgsExtentGroupBox  # Import the new widget
import processing

""" nieuw van Claude """ 
class Top10NLFeaturesLoader(QThread):
    """Thread for loading Top10NL features from OGC API"""
    features_loaded = pyqtSignal(list)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, base_url="https://api.pdok.nl/brt/top10nl/ogc/v1"):
        super().__init__()
        self.base_url = base_url
        
    def run(self):
        """Fetch available collections from OGC API Features service"""
        try:
            collections_url = f"{self.base_url}/collections"
            
            # Make HTTP request
            with urllib.request.urlopen(collections_url, timeout=30) as response:
                data = json.loads(response.read().decode('utf-8'))
            
            # Extract collection IDs
            features = []
            if 'collections' in data:
                for collection in data['collections']:
                    if 'id' in collection:
                        features.append(collection['id'])
            
            # Sort features alphabetically
            features.sort()
            
            QgsMessageLog.logMessage(
                f"Successfully loaded {len(features)} Top10NL features from API", 
                "Top10NL Downloader", 
                Qgis.MessageLevel.Info
            )
            
            self.features_loaded.emit(features)
            
        except urllib.error.URLError as e:
            error_msg = f"Network error loading Top10NL features: {str(e)}"
            QgsMessageLog.logMessage(error_msg, "Top10NL Downloader", Qgis.MessageLevel.Warning)
            self.error_occurred.emit(error_msg)
            
        except json.JSONDecodeError as e:
            error_msg = f"Error parsing Top10NL API response: {str(e)}"
            QgsMessageLog.logMessage(error_msg, "Top10NL Downloader", Qgis.MessageLevel.Warning)
            self.error_occurred.emit(error_msg)
            
        except Exception as e:
            error_msg = f"Unexpected error loading Top10NL features: {str(e)}"
            QgsMessageLog.logMessage(error_msg, "Top10NL Downloader", Qgis.MessageLevel.Critical)
            self.error_occurred.emit(error_msg)


class Top10NLDownloader:
    """Main class for the Top10NL Downloader plugin"""
    
    def __init__(self, iface):
        """Constructor
        
        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        
        # Initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        
        # Initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'Top10NLDownloader_{}.qm'.format(locale))
            
        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)
            
        # Create the dialog and setup UI - pass iface to dialog
        # self.dlg = Top10NLDownloaderDialog(iface)
        # Aangepast door CoPilot:
        self.dlg = Top10NLDownloaderDialog(iface, self)
        # Default values  (removed fixed extent - will be set dynamically)

        self.default_output = os.path.join(QgsProject.instance().homePath(), "Top10NL.gpkg")
        self.default_log = os.path.join(QgsProject.instance().homePath(), "Top10NL.log")
        
        # Declare instance attributes
        self.actions = []
        # self.menu = 'Top10NL Downloader'   Remove me after testing
        self.menu = 'PDOK - OGC API Features-downloaders'
        # self.toolbar = self.iface.addToolBar('Top10NL Downloader')  remove me after testing
        self.toolbar = self.iface.addToolBar('PDOK - OGC API Features-downloaders')
        self.toolbar.setObjectName('PDOK_OGC_API_Features_downloaders')
        
        # Load default features
        self.load_default_features()
        
    def get_current_canvas_extent(self):
        """Get the current extent of the map canvas"""
        try:
            # Get the current extent from the map canvas
            canvas_extent = self.iface.mapCanvas().extent()
            
            # Get the canvas CRS
            canvas_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
            
            # If the canvas CRS is not EPSG:28992, transform it
            if canvas_crs.authid() != "EPSG:28992":
                # Create coordinate transform
                from qgis.core import QgsCoordinateTransform, QgsProject
                
                target_crs = QgsCoordinateReferenceSystem("EPSG:28992")
                transform = QgsCoordinateTransform(canvas_crs, target_crs, QgsProject.instance())
                
                # Transform the extent
                canvas_extent = transform.transformBoundingBox(canvas_extent)
            
            # Format as string (xmin,ymin,xmax,ymax)
            extent_string = f"{canvas_extent.xMinimum()},{canvas_extent.yMinimum()},{canvas_extent.xMaximum()},{canvas_extent.yMaximum()}"
            
            return extent_string, canvas_extent
            
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error getting canvas extent: {str(e)}. Using fallback extent.", 
                "Top10NL Downloader", 
                Qgis.MessageLevel.Warning
            )
            # Fallback to original default extent
            fallback_extent = "154500,462600,155800,463700"
            parts = fallback_extent.split(',')
            fallback_rect = QgsRectangle(
                float(parts[0]), float(parts[1]), 
                float(parts[2]), float(parts[3])
            )
            return fallback_extent, fallback_rect
        
    def add_action(self, icon_path, text, callback, enabled_flag=True,
                  add_to_menu=True, add_to_toolbar=True, status_tip=None,
                  whats_this=None, parent=None):
        """Add a toolbar icon to the toolbar"""
        
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)
        
        if status_tip is not None:
            action.setStatusTip(status_tip)
            
        if whats_this is not None:
            action.setWhatsThis(whats_this)
            
        if add_to_toolbar:
            self.toolbar.addAction(action)
            
        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)
                
        self.actions.append(action)
        
        return action
    
    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI"""
        
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        self.add_action(
            icon_path,
            text="Top10NL Downloader",
            callback=self.run,
            parent=self.iface.mainWindow())
        
        # Connect UI signals
        self.dlg.btn_browse_output.clicked.connect(self.select_output_file)
        # Aangepast door CoPilot
        # self.dlg.btn_browse_log.clicked.connect(self.select_log_file)
        self.dlg.btn_run.clicked.connect(self.start_download)
        self.dlg.btn_refresh_features.clicked.connect(self.refresh_features)
        self.dlg.txt_output.textChanged.connect(self.on_output_file_changed)
        
    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI"""
        for action in self.actions:
            # self.iface.removePluginMenu('Top10NL Downloader', action)
            self.iface.removePluginMenu(self.menu, action) 
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar
        
    def load_default_features(self):
        """Load Top10NL features from OGC API Features service"""
        # Fallback features (your original list) in case API fails
        self.fallback_features = [
            "functioneel_gebied_multivlak",
            "functioneel_gebied_punt",
            "functioneel_gebied_vlak",
            "gebouw_punt",
            "gebouw_vlak",
            "geografisch_gebied_punt",
            "geografisch_gebied_multivlak",
            "geografisch_gebied_vlak",
            "hoogte_lijn",
            "hoogte_punt",
            "inrichtingselement_lijn",
            "inrichtingselement_punt",
            "plaats_multivlak",
            "plaats_punt",
            "plaats_vlak",
            "plantopografie_vlak",
            "registratief_gebied_multivlak",
            "registratief_gebied_vlak",
            "relief_lijn",
            "relief_talud_hoge_zijde_lijn",
            "relief_talud_lage_zijde_lijn",
            "spoorbaandeel_lijn",
            "spoorbaandeel_punt",
            "terrein_vlak",
            "waterdeel_lijn",
            "waterdeel_punt",
            "waterdeel_vlak",
            "wegdeel_hartlijn",
            "wegdeel_hartpunt",
            "wegdeel_lijn",
            "wegdeel_punt",
            "wegdeel_vlak"
        ]
        
        # Initialize with fallback features
        self.features = self.fallback_features.copy()
        
        # Start loading features from API
        self.features_loader = Top10NLFeaturesLoader()
        self.features_loader.features_loaded.connect(self.on_features_loaded)
        self.features_loader.error_occurred.connect(self.on_features_error)
        self.features_loader.start()
        
    def on_features_loaded(self, features):
        """Handle successful loading of features from API"""
        if features:
            self.features = features
            QgsMessageLog.logMessage(
                f"Updated Top10NL features list with {len(features)} items from API", 
                "Top10NL Downloader", 
                Qgis.MessageLevel.Info
            )
            
            # Update dialog if it's already shown
            if hasattr(self, 'dlg') and self.dlg.isVisible():
                self.dlg.populate_features_list(self.features)
    			###### AANPASSEN
                # Set some default selections for commonly used features
                self.dlg.set_default_selection()
        else:
            QgsMessageLog.logMessage(
                "No features received from API, using fallback list", 
                "Top10NL Downloader", 
                Qgis.MessageLevel.Warning
            )
            
    def on_features_error(self, error_message):
        """Handle error loading features from API"""
        QgsMessageLog.logMessage(
            f"Failed to load features from API: {error_message}. Using fallback list.", 
            "Top10NL Downloader", 
            Qgis.MessageLevel.Warning
        )
        
        # Show message to user if dialog is visible
        if hasattr(self, 'dlg') and self.dlg.isVisible():
            self.iface.messageBar().pushMessage(
                "Top10NL Downloader", 
                "Could not load latest features from API. Using default list.", 
                level=Qgis.MessageLevel.Warning,
                duration=5
            )
            # Still populate with fallback features
            self.dlg.populate_features_list(self.features)
            
    def refresh_features(self):
        """Manually refresh the features list from API"""
        if hasattr(self, 'features_loader') and self.features_loader.isRunning():
            return  # Already loading
            
        self.iface.messageBar().pushMessage(
            "Top10NL Downloader", 
            "Refreshing Top10NL features from API...", 
            level=Qgis.MessageLevel.Info,
            duration=3
        )
        
        self.features_loader = Top10NLFeaturesLoader()
        self.features_loader.features_loaded.connect(self.on_features_loaded)
        self.features_loader.error_occurred.connect(self.on_features_error)
        self.features_loader.start()
        
    def select_output_file(self):
        """Open file dialog to select output GPKG file"""
        filename, _ = QFileDialog.getSaveFileName(
            self.dlg, 
            "Select output file", 
            self.default_output, 
            "GeoPackage (*.gpkg)")
            
        if filename:
            self.dlg.txt_output.setText(filename)
            
    def on_output_file_changed(self, text):
        base, _ = os.path.splitext(text)
        self.default_log = base + ".log"
 
    
    def start_download(self):
        """Start the download process"""
        # Get parameters from UI
        output_file = self.dlg.txt_output.text()
        base, _ = os.path.splitext(output_file)
        log_file = base + ".log"
        
        # Get extent from QgsExtentGroupBox
        extent = self.dlg.extent_group.outputExtent()
        extent_coords = [
            extent.xMinimum(),
            extent.yMinimum(),
            extent.xMaximum(),
            extent.yMaximum()
        ]
        
        # Get selected features from list widget instead of text box
        features = self.dlg.get_selected_features()
        
        if not features:
            QMessageBox.warning(
                self.dlg, 
                "No Features Selected", 
                "Please select at least one Top10NL feature to download."
            )
            return
            
        # Check if extent is valid
        if extent.isEmpty() or extent.width() <= 0 or extent.height() <= 0:
            QMessageBox.warning(
                self.dlg, 
                "Invalid Extent", 
                "Please specify a valid extent for the download."
            )
            return
        
        # Determine operation mode
        overwrite = self.dlg.rad_overwrite.isChecked()
        
        # Start the download task
        self.download_task = Top10NLDownloadTask(
            features, 
            extent_coords, 
            output_file, 
            log_file, 
            overwrite,
            self.dlg,
            self.iface
        )
        
        # Start the task
        QgsApplication.taskManager().addTask(self.download_task)
        
        # Show a status message
        self.iface.messageBar().pushMessage(
            "Top10NL Downloader", 
            f"Starting download of {len(features)} Top10NL features: {', '.join(features[:3])}{'...' if len(features) > 3 else ''}", 
            level=Qgis.MessageLevel.Info
        )
            
    def run(self):
        """Run method that performs all the real work"""
        # Set default values in dialog
        self.dlg.txt_output.setText(self.default_output)
        self.on_output_file_changed(self.default_output)
        
        # Get current canvas extent dynamically
        extent_string, extent_rect = self.get_current_canvas_extent()
        
        # Set current canvas extent in the extent group box
        try:
            self.dlg.extent_group.setOutputExtentFromUser(extent_rect, 
                                                        QgsCoordinateReferenceSystem("EPSG:28992"))
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error setting extent: {str(e)}", 
                "Top10NL Downloader", 
                Qgis.MessageLevel.Warning
            )
        # Populate features list widget instead of text area
        self.dlg.populate_features_list(self.features)
        # Set some commonly used features as default selection
        self.dlg.set_default_selection()
        
        # Show the dialog
        self.dlg.show()
        
class Top10NLDownloaderDialog(QDialog):
    def __init__(self, iface=None, plugin=None):
        super().__init__(iface.mainWindow() if iface else None)
        self.iface = iface
        self.plugin = plugin
        self.setWindowTitle("Top10NL Downloader")
        self.resize(500, 700)
        self.setup_ui()
        
    def setup_ui(self):
        """Create the user interface"""
        main_layout = QVBoxLayout()
        
        # Output file
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("Output GPKG:"))
        self.txt_output = QLineEdit()
        output_layout.addWidget(self.txt_output)
        self.btn_browse_output = QPushButton("Browse...")
        output_layout.addWidget(self.btn_browse_output)
        main_layout.addLayout(output_layout)
        
        # Extent - QgsExtentGroupBox
        self.extent_group = QgsExtentGroupBox()
        self.extent_group.setTitle("Extent")
        self.extent_group.setOutputCrs(QgsCoordinateReferenceSystem("EPSG:28992"))
        # Set the map canvas for built-in "From Canvas" functionality
        if self.iface:
            self.extent_group.setMapCanvas(self.iface.mapCanvas())
        main_layout.addWidget(self.extent_group)
        
        # Features section
        features_group = QGroupBox("Top10NL Features")
        features_layout = QVBoxLayout()
        
        # Features list widget with selection controls
        features_controls_layout = QHBoxLayout()
        self.btn_select_all = QPushButton("Select All")
        self.btn_deselect_all = QPushButton("Deselect All")
        self.btn_refresh_features = QPushButton("Refresh from API")
        features_controls_layout.addWidget(self.btn_select_all)
        features_controls_layout.addWidget(self.btn_deselect_all)
        features_controls_layout.addWidget(self.btn_refresh_features)
        features_controls_layout.addStretch()  # Add stretch to push buttons to left
        features_layout.addLayout(features_controls_layout)
        
        # Features list widget
        self.list_features = QListWidget()
        self.list_features.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.list_features.setMinimumHeight(100)
        self.list_features.setMaximumHeight(200)  # Set maximum height
        # Scrollbar policy is automatic by default - shows when needed
        features_layout.addWidget(self.list_features)
        
        features_group.setLayout(features_layout)
        main_layout.addWidget(features_group)
        
        # Operation mode
        op_group = QGroupBox("Operation Mode")
        op_layout = QHBoxLayout()
        self.rad_overwrite = QRadioButton("Overwrite")
        self.rad_append = QRadioButton("Append")
        self.rad_append.setChecked(True)
        op_layout.addWidget(self.rad_append)
        op_layout.addWidget(self.rad_overwrite)
        op_group.setLayout(op_layout)
        main_layout.addWidget(op_group)
        
        # Progress
        main_layout.addWidget(QLabel("Progress:"))
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)
        
        # Log window
        main_layout.addWidget(QLabel("Log:"))
        self.txt_log_output = QTextEdit()
        self.txt_log_output.setReadOnly(True)
        self.txt_log_output.setMinimumHeight(150)
        main_layout.addWidget(self.txt_log_output)
        
        # Buttons
        buttons_layout = QHBoxLayout()
        self.btn_run = QPushButton("Run")
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.close)
        buttons_layout.addWidget(self.btn_run)
        buttons_layout.addWidget(self.btn_close)
        main_layout.addLayout(buttons_layout)
        
        self.setLayout(main_layout)
        
        # Connect selection buttons
        self.btn_select_all.clicked.connect(self.select_all_features)
        self.btn_deselect_all.clicked.connect(self.deselect_all_features)
        
    def populate_features_list(self, features):
        """Populate the features list widget with available features"""
        self.list_features.clear()
        
        for feature in sorted(features):
            item = QListWidgetItem(feature)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.list_features.addItem(item)
            
    def get_selected_features(self):
        """Get list of selected features"""
        selected_features = []
        for i in range(self.list_features.count()):
            item = self.list_features.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected_features.append(item.text())
        return selected_features
        
    def select_all_features(self):
        """Select all features in the list"""
        for i in range(self.list_features.count()):
            item = self.list_features.item(i)
            item.setCheckState(Qt.CheckState.Checked)
            
    def deselect_all_features(self):
        """Deselect all features in the list"""
        for i in range(self.list_features.count()):
            item = self.list_features.item(i)
            item.setCheckState(Qt.CheckState.Unchecked)
            
    def set_default_selection(self, default_features=None):
        """Set default selected features (useful for common features)"""
        if default_features is None:
            # Default to some commonly used Top10NL features
            default_features = ["wegdeel_vlak", "gebouw_vlak", "waterdeel_vlak", "terrein_vlak"]
            
        for i in range(self.list_features.count()):
            item = self.list_features.item(i)
            if item.text() in default_features:
                item.setCheckState(Qt.CheckState.Checked)
                
    def select_all_by_default(self, select_all=False):
        """Option to select all features by default"""
        check_state = Qt.CheckState.Checked if select_all else Qt.CheckState.Unchecked
        for i in range(self.list_features.count()):
            item = self.list_features.item(i)
            item.setCheckState(check_state)
            
    def update_progress(self, value):
        """Update the progress bar - called from task thread"""
        self.progress_bar.setValue(value)
        
    def append_log(self, message):
        """Append message to log output - called from task thread"""
        self.txt_log_output.append(message)
        # Auto-scroll to bottom
        scrollbar = self.txt_log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        

class Top10NLDownloadTask(QgsTask):
    """Background task for downloading Top10NL features"""
    
    # Add custom signals for real-time updates
    progress_updated = pyqtSignal(int)  # For progress percentage
    log_updated = pyqtSignal(str)       # For log messages
    
    def __init__(self, features, extent, output_file, log_file, overwrite, dialog, iface):
        super().__init__("Top10NL Download Task", QgsTask.Flag.CanCancel)
        self.features = features
        self.extent = extent
        self.output_file = output_file
        self.log_file = log_file
        self.overwrite = overwrite
        self.dlg = dialog
        self.iface = iface
        self.exception = None
        self.log_lines = []
        
        # Connect signals to dialog updates
        if self.dlg:
            self.progress_updated.connect(self.dlg.update_progress)
            self.log_updated.connect(self.dlg.append_log)
        
    def log(self, message):
        """Add message to log file and UI"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"{timestamp} - {message}"
        self.log_lines.append(log_message)
        
        # Emit signal to update dialog log in real-time
        self.log_updated.emit(log_message)
        
        # Write to log file immediately
        try:
            with open(self.log_file, 'a', encoding='utf-8') as log_file:
                log_file.write(log_message + "\n")
        except Exception as e:
            QgsMessageLog.logMessage(f"Error writing to log: {str(e)}", "Top10NL Downloader", Qgis.MessageLevel.Warning)
            
    def run(self):
        """Run the download task"""
        try:
            # Initialize log file
            with open(self.log_file, 'a', encoding='utf-8') as log_file:
                log_file.write("\n\n")
                log_file.write(f"{datetime.datetime.now().strftime('%Y-%m-%d')}\n")
                log_file.write("Top10NL-features importeren in GeoPackage\n")
                log_file.write("\n")
                log_file.write("-------------------------\n")
            
            self.log(f"Starting Top10NL download process with {len(self.features)} features")
            self.log(f"Extent: {self.extent[0]},{self.extent[1]},{self.extent[2]},{self.extent[3]}")
            self.log(f"Processing mode: {'overwrite layer' if self.overwrite else 'append to layer'}")
            
            start_time = datetime.datetime.now()
            self.log(f"Script start: {start_time.strftime('%H:%M:%S')}")
            self.log("-------------------------\n")
            
            # Process each feature
            total_features = len(self.features)
            
            for i, feature in enumerate(self.features):
                if self.isCanceled():
                    return False
                    
                feature = feature.strip()
                if not feature:
                    continue
                    
                # Calculate and emit progress
                progress = int((i / total_features) * 100)
                self.setProgress(progress)  # For QGIS task manager
                self.progress_updated.emit(progress)  # For dialog progress bar
                
                self.log(f"  Top10NL-object: {feature}")
                self.log(f"  Extent: {self.extent[0]},{self.extent[1]},{self.extent[2]},{self.extent[3]}")
                
                start_feature_time = datetime.datetime.now()
                self.log(f"  Start Time: {start_feature_time.strftime('%H:%M:%S')}")
                
                params = {
                    'INPUT': f'OAPIF:https://api.pdok.nl/brt/top10nl/ogc/v1/collections/{feature}',
                    'OUTPUT': self.output_file,
                    'OPTIONS': f'-{"overwrite" if self.overwrite else "append"} -oo CRS=EPSG:28992 -spat {self.extent[0]} {self.extent[1]} {self.extent[2]} {self.extent[3]} -s_srs EPSG:28992 -t_srs EPSG:28992'
                }
                
                try:
                    # Nog geen idee hoe je hier foute conversies 
                    processing.run("gdal:convertformat", params)
                    self.log(f"  Feature {feature} processed")
                except Exception as e:
                    self.log(f"  Error processing feature {feature}: {str(e)}")
                
                end_feature_time = datetime.datetime.now()
                self.log(f"  Finish Time: {end_feature_time.strftime('%H:%M:%S')}")
                self.log("-------------------------")
            
            # Final progress update
            self.setProgress(100)
            self.progress_updated.emit(100)
            
            # Deduplicate features by 'ID' in each layer if appending
            if not self.overwrite:
                self.log("Removing duplicate features based on 'ID' attribute...")
                for feature in self.features:
                    layer_path = f"{self.output_file}|layername={feature}"
                    layer = QgsVectorLayer(layer_path, feature, "ogr")
                    if not layer.isValid():
                        self.log(f"  Could not open layer {feature} for deduplication.")
                        continue
                    try:
                        # https://docs.qgis.org/3.40/en/docs/user_manual/processing_algs/qgis/vectorgeneral.html#delete-duplicates-by-attribute
                        dedup_result = processing.run(
                            "native:removeduplicatesbyattribute",
                            {
                                "INPUT": layer,
                                "FIELDS": ["ID"],
                                "OUTPUT": 'TEMPORARY_OUTPUT'  # Output to memory first
                            }
                        )
                        # Overwrite the layer in the GeoPackage with the deduplicated version
                        # toevoegen: alleen saven wanneer er duplicaten waren, anders is wegschrijven niet nodig
                        # wegschrijven gaat niet goed
                        processing.run(
                            # "native:saveselectedfeatures",
                            "native:savefeatures",
                            {
                                # Copilot gaat denk ik mis met de input
                                # "INPUT": layer,
                                "INPUT": dedup_result["OUTPUT"],
                                "LAYER_NAME": feature,
                                "LAYER_OPTIONS": '',
                                "ACTION_ON_EXISTING_FILE": 1,    # create or overwrite layer
                                # hier gaat het fout.
                                # "OUTPUT": layer_path
                                "OUTPUT": self.output_file
                            }
                        )
                        # dit logging-deel moet herschreven worden.
                        # 1. er wordt niets weggeschreven
                        # 2. dedup_result["DUPLICATE_COUNT"] danwel dedup_result["RETAINED_COUNT"] gebruiken in de logging
                        self.log(f"  {dedup_result['DUPLICATE_COUNT']} Duplicates features removed from {feature}; {dedup_result['RETAINED_COUNT']} features remaining")
                    except Exception as e:
                        self.log(f"  Error removing duplicates from {feature}: {str(e)}")

            end_time = datetime.datetime.now()
            self.log(f"Script end: {end_time.strftime('%H:%M:%S')}")
            self.log(f"Total time: {end_time - start_time}")
            self.log("Finished")
            self.log("-------------------------")
            
            return True
            
        except Exception as e:
            self.exception = e
            self.log(f"Error during download: {str(e)}")
            return False
    
    def finished(self, result):
        """Called when the task is complete"""
        if result:
            # Success message
            self.iface.messageBar().pushMessage(
                "Top10NL Downloader", 
                f"Downloaded {len(self.features)} Top10NL features successfully", 
                level=Qgis.MessageLevel.Success
            )
            
            # Ask if user wants to add the layers to the project
            if self.iface:
                reply = QMessageBox.question(
                    None, 
                    "Top10NL Downloader", 
                    "Do you want to add the downloaded layers to the map?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                
                root = QgsProject.instance().layerTreeRoot()
                gpkg_name = os.path.basename(self.output_file)
                group_layer_name = f"{gpkg_name} (PDOK-OAPIF-download)"
                group_layer = root.findGroup(group_layer_name)
                if group_layer:
                    for child in group_layer.children():
                        if hasattr(child, 'layer') and child.layer() is not None:
                            existing_layer = child.layer()
                            # Only refresh layers from this GeoPackage
                            if self.output_file in existing_layer.source():
                                existing_layer.triggerRepaint()

                if reply == QMessageBox.StandardButton.Yes:
                    # group layer: search for existing group or create new one
                    if not group_layer:
                        group_layer = QgsLayerTreeGroup(group_layer_name)
                        root.insertChildNode(0, group_layer)

                    # Build a list of (layer, geometry_type) for existing layers in the group
                    existing_layers = []
                    for child in group_layer.children():
                        if hasattr(child, 'layer') and child.layer() is not None:
                            existing_layers.append((child.layer(), child.layer().geometryType()))

                    # Prepare new layers and their geometry types
                    new_layers = []
                    for feature in self.features:
                        feature = feature.strip()
                        if not feature:
                            continue
                        layer_source = f"{self.output_file}|layername={feature}"
                        layer = QgsVectorLayer(layer_source, f"Top10NL {feature}", "ogr")
                        if layer.isValid():
                            # Check if this layer already exists in the group (by source)
                            already_in_group = False
                            for child in group_layer.children():
                                if hasattr(child, 'layer') and child.layer() is not None:
                                    existing_layer = child.layer()
                                    if (existing_layer.source() == layer_source or
                                        existing_layer.dataProvider().dataSourceUri() == layer_source):
                                        already_in_group = True
                                        break
                            if not already_in_group:
                                QgsProject.instance().addMapLayer(layer, False)
                                new_layers.append((layer, layer.geometryType()))
                            # Optionally, refresh the layer if it already exists
                            else:
                                existing_layer.triggerRepaint()
                        else:
                            QgsMessageLog.logMessage(
                                f"Layer {feature} is not valid",
                                "Top10NL Downloader",
                                Qgis.MessageLevel.Warning
                            )

                    # Helper: geometryType() returns 0=Point, 1=Line, 2=Polygon
                    # Insert new layers in correct order: points (top), lines (middle), polygons (bottom)
                    for new_layer, new_geom in new_layers:
                        # Find the correct index to insert
                        insert_index = 0
                        for idx, (existing_layer, existing_geom) in enumerate(existing_layers):
                            # If new layer should be below this existing layer, break
                            if new_geom > existing_geom:
                                insert_index = idx + 1
                        # Insert at the found index
                        group_layer.insertChildNode(insert_index, QgsLayerTreeLayer(new_layer))
                        # Also update existing_layers to reflect the new state
                        existing_layers.insert(insert_index, (new_layer, new_geom))
        else:
            # Show error
            if self.exception:
                QgsMessageLog.logMessage(
                    f"Top10NL Download task failed: {str(self.exception)}", 
                    "Top10NL Downloader", 
                    Qgis.MessageLevel.Critical
                )
                
                self.iface.messageBar().pushMessage(
                    "Top10NL Downloader", 
                    f"Error during download: {str(self.exception)}", 
                    level=Qgis.MessageLevel.Critical
                )

