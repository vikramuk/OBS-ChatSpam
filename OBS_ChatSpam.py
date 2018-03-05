#
# Project     OBS Twitch Chat Spam Script
# @author     David Madison
# @link       github.com/dmadison/OBS-ChatSpam
# @license    GPLv3 - Copyright (c) 2018 David Madison
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import obspython as obs
import socket
from time import sleep


class TwitchIRC:
	def __init__(self, chan="", nick="", passw="", host="irc.twitch.tv", port=6667):
		self.channel = chan
		self.nickname = nick
		self.password = passw
		self.host = host
		self.port = port
		self.max_rate = 20/30

		self.__sock = socket.socket()

	def connect(self):
		self.__sock = socket.socket()
		self.__sock.connect((self.host, self.port))
		if self.password is not "":
			self.__sock.send("PASS {}\r\n".format(self.password).encode("utf-8"))
		self.__sock.send("NICK {}\r\n".format(self.nickname).encode("utf-8"))
		self.__sock.send("JOIN #{}\r\n".format(self.channel).encode("utf-8"))

		auth_response = self.read()

		if "Welcome, GLHF!" not in auth_response:
			raise UserWarning("Authentication Error!")

	def disconnect(self):
		self.__sock.shutdown(socket.SHUT_RDWR)
		self.__sock.close()

	def chat(self, msg):
		self.__sock.send("PRIVMSG #{} :{}\r\n".format(self.channel, msg).encode("utf-8"))
		print("Sent \'" + msg + "\'", "as", self.nickname, "in #" + self.channel)
		sleep(self.max_rate)  # Simple way to avoid the rate limit

	def read(self):
		response = self.__read_socket()
		while self.__ping(response):
			response = self.__read_socket()
		return response.rstrip()

	def __read_socket(self):
		return self.__sock.recv(1024).decode("utf-8")

	def __ping(self, msg):
		if msg[:4] == "PING":
			self.__pong(msg[4:])
			return True
		return False

	def __pong(self, host):
		self.__sock.send(("PONG" + host).encode("utf-8"))

twitch = TwitchIRC()

class ChatMessage:
	messages = []
	max_description_length = 32

	def __init__(self, msg, position, obs_settings, irc=twitch):
		self.text = msg
		self.irc = irc

		self.obs_data = obs_settings

		self.position = position
		self.hotkey_id = obs.OBS_INVALID_HOTKEY_ID
		self.hotkey_saved_key = None

		self.load_hotkey()
		self.register_hotkey()
		self.save_hotkey()

	def __del__(self):
		self.cleanup()

	def cleanup(self):
		self.deregister_hotkey()
		self.release_memory()

	def release_memory(self):
		obs.obs_data_array_release(self.hotkey_saved_key)

	def new_text(self, msg):
		self.text = msg
		self.deregister_hotkey()
		self.register_hotkey()

	def new_position(self, pos):
		self.deregister_hotkey()
		self.unsave_hotkey()
		self.position = pos
		self.register_hotkey()

	def load_hotkey(self):
		self.hotkey_saved_key = obs.obs_data_get_array(self.obs_data, "chat_hotkey_" + str(self.position))

	def register_hotkey(self):
		if len(self.text) > ChatMessage.max_description_length:
			key_description = self.text[:ChatMessage.max_description_length - 3] + "..."
		else:
			key_description = self.text
		key_description = "Chat \'" + key_description + "\'"

		self.callback = lambda pressed: self.send(pressed)  # Small hack to get around the callback signature reqs.
		self.hotkey_id = obs.obs_hotkey_register_frontend("chat_hotkey", key_description, self.callback)
		obs.obs_hotkey_load(self.hotkey_id, self.hotkey_saved_key)

	def deregister_hotkey(self):
		obs.obs_hotkey_unregister(self.callback)

	def save_hotkey(self):
		self.hotkey_saved_key = obs.obs_hotkey_save(self.hotkey_id)
		obs.obs_data_set_array(self.obs_data, "chat_hotkey_" + str(self.position), self.hotkey_saved_key)

	def unsave_hotkey(self):
		obs.obs_data_erase(self.obs_data, "chat_hotkey_" + str(self.position))

	def send(self, pressed=True):
		if pressed:
			self.irc.connect()
			self.irc.chat(self.text)
			self.irc.disconnect()

	@staticmethod
	def check_messages(new_msgs, settings):
		# Check if list hasn't changed
		if len(new_msgs) == len(ChatMessage.messages):
			num_diff = 0
			diff_index = None

			for index, msg in enumerate(ChatMessage.messages):
				if new_msgs[index] != msg.text:
					num_diff += 1
					diff_index = index
					if num_diff > 1:
						break

			if num_diff == 0:
				return  # Lists identical
			elif num_diff == 1:
				ChatMessage.messages[diff_index].new_text(new_msgs[diff_index])
				return  # Single entry modified

		# Check if objects already exist, otherwise create them
		new_list = []
		for pos, msg in enumerate(new_msgs):
			for msg_obj in ChatMessage.messages:
				if msg == msg_obj.text:
					new_list.append(msg_obj)
					break
			else:
				new_list.append(ChatMessage(msg, pos, settings))

		# Clean up old objects
		for msg in ChatMessage.messages:
			for msg_new in new_msgs:
				if msg.text == msg_new:
					break
			else:
				msg.cleanup()
				msg.unsave_hotkey()

		# Assign to master array and reindex
		ChatMessage.messages = new_list
		ChatMessage.__reindex_messages()

	@staticmethod
	def __reindex_messages():
		for index, msg in enumerate(ChatMessage.messages):
			msg.new_position(index)

		for msg in ChatMessage.messages:  # Separate loop as to avoid memory overwrites
			msg.save_hotkey()


# ------------------------------------------------------------

# OBS Script Functions

def script_description():
	return "<b>Twitch Chat Spam</b>" + \
			"<hr>" + \
			"Python script for sending messages to Twitch chat using OBS hotkeys." + \
			"<br/><br/>" + \
			"Made by David Madison" + \
			"<br/>" + \
			"www.partsnotincluded.com"

def script_update(settings):
	global chat_text

	twitch.channel = obs.obs_data_get_string(settings, "channel").lower()
	twitch.nickname = obs.obs_data_get_string(settings, "user").lower()
	twitch.password = obs.obs_data_get_string(settings, "oauth").lower()
	chat_text = obs.obs_data_get_string(settings, "chat_text")

	obs_messages = obs.obs_data_get_array(settings, "messages")
	num_messages = obs.obs_data_array_count(obs_messages)

	messages = []
	for i in range(num_messages):  # Convert C array to Python list
		message_object = obs.obs_data_array_item(obs_messages, i)
		messages.append(obs.obs_data_get_string(message_object, "value"))

	ChatMessage.check_messages(messages, settings)

	#print("Settings JSON", obs.obs_data_get_json(settings))

def script_properties():
	props = obs.obs_properties_create()

	obs.obs_properties_add_text(props, "channel", "Channel", obs.OBS_TEXT_DEFAULT)
	obs.obs_properties_add_text(props, "user", "User", obs.OBS_TEXT_DEFAULT)
	obs.obs_properties_add_text(props, "oauth", "Oauth", obs.OBS_TEXT_PASSWORD)

	obs.obs_properties_add_editable_list(props, "messages", "Messages", obs.OBS_EDITABLE_LIST_TYPE_STRINGS, "", "")

	return props
#
def script_save(settings):
	for message in ChatMessage.messages:
		message.save_hotkey()

def script_unload():
	for message in ChatMessage.messages:
		message.cleanup()
