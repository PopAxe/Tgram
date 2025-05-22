# File to save and change the properties of chats that we want to listen to.
import logging
import json
import os

class ChatProperties:
    VALID_MODELS = ["chatgpt", "gemini"]
    chat_ids = {}
    # For documentation mostly.
    ## chat_id_tempate = {
    ##     "chat": "",
    ##     "model": VALID_MODELS[0],
    ##     "listening": False,
    ##     "chat_title" : "",
    ## }
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.load_chats()
        
    def set_chat(self, chat_id: str="", model: str=None, listening: bool=False, chat_title: str=""):
        if model is None:
            model = self.VALID_MODELS[0]
        if model not in self.VALID_MODELS:
            self.logger.info(f"requested '{model}' isn't valid, setting model to '{self.VALID_MODELS[0]}'")
            model = self.VALID_MODELS[0]
        if chat_title == None:
            chat_title = ""
        if chat_id in self.chat_ids:
            self.chat_ids[chat_id]["model"] = model
            self.chat_ids[chat_id]["listening"] = listening
            self.chat_ids[chat_id]["chat_title"] = chat_title
        else:
            self.chat_ids[chat_id] = {
                "chat": chat_id,
                "model": model,
                "listening": listening,
                "chat_title": chat_title,
            }
        self.save_chats()

    def save_chats(self):
        import json
        self.logger.info("Saving chat properties to JSON")
        try:
            with open("chat_properties.json", "w") as f:
                json.dump(self.chat_ids, f, indent=2)
            self.logger.info("Saved chat properties")
        except Exception as e:
            self.logger.error(f"Error saving chat properties: {e}")

    def load_chats(self):
        if os.path.exists("chat_properties.json"):
            try:
                with open("chat_properties.json", "r") as f:
                    self.chat_ids = json.load(f)
                self.logger.info(f"Loaded {len(self.chat_ids)} chat properties")
            except Exception as e:
                self.logger.error(f"Error loading chat properties: {e}")
                self.chat_ids = {}

    def get_chat(self, chat_id: str=""):
        if chat_id in self.chat_ids:
            return self.chat_ids[chat_id]
        else:
            return None