"""
Copyright 2011-2016 Ryan Fobel and Christian Fobel

This file is part of MicroDrop.

MicroDrop is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

MicroDrop is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with MicroDrop.  If not, see <http://www.gnu.org/licenses/>.
"""
from datetime import datetime
import pdb
import pkg_resources
import webbrowser

from pygtkhelpers.proxy import proxy_for
from microdrop_utility import wrap_string
from microdrop_utility.gui import DEFAULTS
import gobject
import gtk
try:
    import pudb
    PUDB_AVAILABLE = True
except ImportError:
    PUDB_AVAILABLE = False

from ..plugin_manager import (IPlugin, SingletonPlugin, implements,
                              PluginGlobals, ScheduleRequest, ILoggingPlugin,
                              emit_signal, get_service_instance_by_name)
from ..app_context import get_app
import logging

logger = logging.getLogger(__name__)
from .. import glade_path



PluginGlobals.push_env('microdrop')


class MainWindowController(SingletonPlugin):
    implements(IPlugin)
    implements(ILoggingPlugin)

    builder_path = glade_path().joinpath("main_window.glade")

    def __init__(self):
        self._shutting_down_latch = False
        self.name = "microdrop.gui.main_window_controller"
        self.builder = None
        self.view = None
        self.label_control_board_status = None
        self.label_experiment_id = None
        self.label_device_name = None
        self.label_protocol_name = None
        self.checkbutton_realtime_mode = None
        self.menu_tools = None
        self.menu_view = None
        self.step_start_time = None
        self.step_timeout_id = None
        gtk.link_button_set_uri_hook(self.on_url_clicked)

        builder = gtk.Builder()
        builder.add_from_file(glade_path().joinpath("text_input_dialog.glade"))
        self.text_input_dialog = builder.get_object("window")
        self.text_input_dialog.textentry = builder.get_object("textentry")
        self.text_input_dialog.label = builder.get_object("label")

    def enable_keyboard_shortcuts(self):
        for group_i in self.accel_groups:
            self.view.add_accel_group(group_i)

    def disable_keyboard_shortcuts(self):
        for group_i in self.accel_groups:
            self.view.remove_accel_group(group_i, cached=True)

    def on_plugin_enable(self):
        app = get_app()
        app.builder.add_from_file(self.builder_path)
        self.view = app.builder.get_object("window")

        self.view._add_accel_group = self.view.add_accel_group
        def add_accel_group(accel_group):
            self.view._add_accel_group(accel_group)
            if not hasattr(self, 'accel_groups'):
                self.accel_groups = set()
            self.accel_groups.add(accel_group)
        self.view.add_accel_group = add_accel_group

        self.view._remove_accel_group = self.view.remove_accel_group
        def remove_accel_group(accel_group, cached=True):
            self.view._remove_accel_group(accel_group)
            if not cached and hasattr(self, 'accel_groups'):
                self.accel_groups.remove(accel_group)
        self.view.remove_accel_group = remove_accel_group

        self.vbox2 = app.builder.get_object('vbox2')
        self.view.set_icon_from_file(
            pkg_resources.resource_filename('microdrop', 'microdrop.ico'))
        DEFAULTS.parent_widget = self.view

        for widget_name in ('box_step', 'checkbutton_realtime_mode',
                            'label_control_board_status', 'label_device_name',
                            'label_experiment_id', 'label_protocol_name',
                            'label_protocol_name', 'label_step_time',
                            'menu_experiment_logs', 'menu_tools', 'menu_view',
                            'button_open_log_directory', 'button_open_log_notes'):
            setattr(self, widget_name, app.builder.get_object(widget_name))

        app.signals["on_menu_quit_activate"] = self.on_destroy
        app.signals["on_menu_about_activate"] = self.on_about
        app.signals["on_menu_online_help_activate"] = self.on_menu_online_help_activate
        app.signals["on_menu_experiment_logs_activate"] = \
            self.on_menu_experiment_logs_activate
        app.signals["on_window_destroy"] = self.on_destroy
        app.signals["on_window_delete_event"] = self.on_delete_event
        app.signals["on_checkbutton_realtime_mode_button_press_event"] = \
                self.on_realtime_mode_toggled
        app.signals["on_button_open_log_directory_clicked"] = \
                self.on_button_open_log_directory
        app.signals["on_button_open_log_notes_clicked"] = \
                self.on_button_open_log_notes
        app.signals["on_menu_app_options_activate"] = self.on_menu_app_options_activate
        app.signals["on_menu_manage_plugins_activate"] = self.on_menu_manage_plugins_activate

        self.builder = gtk.Builder()
        self.builder.add_from_file(glade_path().joinpath('about_dialog.glade'))
        app.main_window_controller = self
        self.protocol_list_view = None

        self.checkbutton_realtime_mode.set_sensitive(False)
        self.button_open_log_directory.set_sensitive(False)
        self.button_open_log_notes.set_sensitive(False)
        self.menu_experiment_logs.set_sensitive(False)

        if app.config.data.get('advanced_ui', False):
            import IPython

            self.debug_menu_item = gtk.MenuItem('Debug...')
            self.debug_menu_item.show()
            self.ipython_menu_item = gtk.MenuItem('IPython...')
            self.ipython_menu_item.show()

            def activate_debugger(parent):
                try:
                    plugin = get_service_instance_by_name(
                        'wheelerlab.dmf_control_board')
                    control_board = plugin.control_board
                except KeyError:
                    plugin = None
                    control_board = None

                if PUDB_AVAILABLE:
                    pudb.set_trace()
                else:
                    pdb.set_trace()
            self.debug_menu_item.connect('activate', lambda *args:
                                         activate_debugger(self))
            self.ipython_menu_item.connect('activate', lambda *args:
                                           IPython.embed())
            self.menu_tools.append(self.debug_menu_item)
            self.menu_tools.append(self.ipython_menu_item)

    def main(self):
        gtk.main()

    def get_text_input(self, title, label, default_value=""):
        self.text_input_dialog.set_title(title)
        self.text_input_dialog.label.set_markup(label)
        self.text_input_dialog.textentry.set_text(default_value)
        self.text_input_dialog.set_transient_for(self.view)
        response = self.text_input_dialog.run()
        self.text_input_dialog.hide()
        name = ""
        if response == gtk.RESPONSE_OK:
            name = self.text_input_dialog.textentry.get_text()
        return name

    def on_delete_event(self, widget, data=None):
        if not self._shutting_down_latch:
            self._shutting_down_latch = True

            app = get_app()
            data = app.get_app_values()
            allocation = self.view.get_allocation()
            data['width'] = allocation.width
            data['height'] = allocation.height
            data['x'], data['y'] = self.view.get_position()
            app.set_app_values(data)

            emit_signal("on_app_exit")
            hub = get_service_instance_by_name('wheelerlab.zmq_hub_plugin',
                                               env='microdrop')
            hub.on_plugin_disable()

    def on_destroy(self, widget, data=None, return_code=0):
        self.on_delete_event(None)
        gtk.main_quit()
        raise SystemExit(return_code)

    def on_about(self, widget, data=None):
        app = get_app()
        dialog = self.builder.get_object("about_dialog")
        dialog.set_transient_for(app.main_window_controller.view)
        dialog.set_version(app.version)
        dialog.run()
        dialog.hide()

    def on_menu_online_help_activate(self, widget, data=None):
        webbrowser.open_new_tab('http://microfluidics.utoronto.ca/microdrop/wiki/UserGuide')

    def on_menu_manage_plugins_activate(self, widget, data=None):
        service = get_service_instance_by_name(
                    'microdrop.gui.plugin_manager_controller', env='microdrop')
        service.dialog.window.set_transient_for(self.view)
        service.dialog.run()

    def on_menu_experiment_logs_activate(self, widget, data=None):
        app = get_app()
        app.experiment_log_controller.on_window_show(widget, data)

    def on_button_open_log_directory(self, widget, data=None):
        '''
        Open selected experiment log directory in system file browser.
        '''
        app = get_app()
        app.experiment_log.get_log_path().launch()

    def on_button_open_log_notes(self, widget, data=None):
        '''
        Open selected experiment log notes.
        '''
        app = get_app()
        notes_path = app.experiment_log.get_log_path() / 'notes.txt'
        if not notes_path.isfile():
            notes_path.touch()
        notes_path.launch()

    def on_realtime_mode_toggled(self, widget, data=None):
        realtime_mode = not self.checkbutton_realtime_mode.get_active()
        self.checkbutton_realtime_mode.set_active(realtime_mode)
        app = get_app()
        app.set_app_values({'realtime_mode': realtime_mode})
        return True

    def on_menu_app_options_activate(self, widget, data=None):
        from app_options_controller import AppOptionsController

        AppOptionsController().run()

    def on_warning(self, record):
        self.warning(record.message)

    def on_error(self, record):
        self.error(record.message)

    def on_critical(self, record):
        self.error(record.message)

    def error(self, message, title="Error"):
        dialog = gtk.MessageDialog(self.view,
                                   gtk.DIALOG_DESTROY_WITH_PARENT,
                                   gtk.MESSAGE_ERROR,
                                   gtk.BUTTONS_CLOSE, message)
        dialog.set_title(title)
        result = dialog.run()
        dialog.destroy()
        return result

    def warning(self, message, title="Warning"):
        dialog = gtk.MessageDialog(self.view,
                                   gtk.DIALOG_DESTROY_WITH_PARENT,
                                   gtk.MESSAGE_WARNING,
                                   gtk.BUTTONS_CLOSE, message)
        dialog.set_title(title)
        result = dialog.run()
        dialog.destroy()
        return result

    def question(self, message, title=""):
        dialog = gtk.MessageDialog(self.view,
                                   gtk.DIALOG_DESTROY_WITH_PARENT,
                                   gtk.MESSAGE_QUESTION,
                                   gtk.BUTTONS_YES_NO, message)
        dialog.set_title(title)
        result = dialog.run()
        dialog.destroy()
        return result

    def info(self, message, title=""):
        dialog = gtk.MessageDialog(self.view,
                                   gtk.DIALOG_DESTROY_WITH_PARENT,
                                   gtk.MESSAGE_INFO,
                                   gtk.BUTTONS_CLOSE, message)
        dialog.set_title(title)
        result = dialog.run()
        dialog.destroy()
        return result

    def on_app_options_changed(self, plugin_name):
        app = get_app()
        if plugin_name == app.name:
            data = app.get_data(app.name)
            if 'realtime_mode' in data:
                proxy = proxy_for(self.checkbutton_realtime_mode)
                proxy.set_widget_value(data['realtime_mode'])

    def on_url_clicked(self, widget, data):
        logger.debug("URL clicked: %s" % data)
        webbrowser.open_new_tab(data)

    def get_protocol_string(self, protocol=None):
        if protocol is None:
            protocol = get_app().protocol
        if protocol is None:
            return 'Protocol: None'
        return 'Protocol: %s' % protocol.name

    def update_label(self, label, obj=None, modified=False, get_string=str):
        message = get_string(obj)
        if modified:
            message += ' <b>[modified]</b>'
        #label.set_text(wrap_string(message, 30, "\n\t"))
        label.set_markup(wrap_string(message, 60, "\n\t"))

    def update_protocol_name_label(self, obj=None, **kwargs):
        _kwargs = kwargs.copy()
        _kwargs['get_string'] = self.get_protocol_string
        self.update_label(self.label_protocol_name, obj=obj, **_kwargs)

    def on_protocol_swapped(self, old_protocol, protocol):
        self.on_protocol_changed()

    def on_protocol_changed(self):
        app = get_app()
        self.update_protocol_name_label(modified= \
                                        app.protocol_controller.modified)

    def on_experiment_log_changed(self, experiment_log):
        self.button_open_log_directory.set_sensitive(True)
        self.button_open_log_notes.set_sensitive(True)
        if experiment_log:
            self.label_experiment_id.set_text("Experiment: %s (%s)" %
                                              (str(experiment_log.experiment_id),
                                              experiment_log.uuid))

    def get_device_string(self, device=None):
        if device is None:
            device = get_app().dmf_device
        if device is None:
            return 'Device: None'
        return 'Device: %s' % device.name

    def update_device_name_label(self, obj=None, **kwargs):
        _kwargs = kwargs.copy()
        _kwargs['get_string'] = self.get_device_string
        self.update_label(self.label_device_name, obj=obj, **_kwargs)

    def on_dmf_device_swapped(self, old_dmf_device, dmf_device):
        self.checkbutton_realtime_mode.set_sensitive(True)
        self.menu_experiment_logs.set_sensitive(True)
        self.update_device_name_label(dmf_device, modified=
                                      get_app().dmf_device_controller.modified)

    def on_dmf_device_changed(self, dmf_device):
        self.update_device_name_label(modified=True)

    def on_dmf_device_saved(self, dmf_device, device_path):
        self.update_device_name_label(modified=False)

    def get_schedule_requests(self, function_name):
        """
        Returns a list of scheduling requests (i.e., ScheduleRequest
        instances) for the function specified by function_name.
        """
        if function_name == 'on_plugin_enable':
            return [ScheduleRequest(self.name, 'microdrop.app')]
        elif function_name == 'on_protocol_swapped':
            # make sure app reference is updated first
            return [ScheduleRequest('microdrop.app', self.name)]
        return []

    def on_protocol_pause(self):
        '''
        Reset step timer when protocol is stopped.
        '''
        self.reset_step_timeout()

    def on_step_run(self):
        '''
         - Store start time of step.
         - Start periodic timer to update the step time label.
        '''
        self.step_start_time = datetime.utcnow()

        def update_time_label():
            app = get_app()
            if not app.running:
                # Protocol is no longer running.  Stop step timer.
                self.reset_step_timeout()
                return False
            elapsed_time = datetime.utcnow() - self.step_start_time
            self.label_step_time.set_text(str(elapsed_time).split('.')[0])
            return True

        # A new step is starting to run.  Reset step timer.
        self.reset_step_timeout()
        # Update step time label once per second.
        self.step_timeout_id = gtk.timeout_add(1000, update_time_label)
        emit_signal('on_step_complete', [self.name, None])

    def reset_step_timeout(self):
        '''
         - Stop periodic callback.
         - Clear step time label.
        '''
        if self.step_timeout_id is not None:
            gobject.source_remove(self.step_timeout_id)
        self.label_step_time.set_text('-')

PluginGlobals.pop_env()
