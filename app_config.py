import logging


# The `BotConfiguration` class is designed to load and verify configuration settings from a
# file, checking for missing values and logging errors if necessary.
class BotConfiguration:
    def __init__(self, config_filename, logger: logging.Logger) -> None:
        self.filename = config_filename
        self.CHAT_GPT_KEY = ""
        self.BOT_KEY = ""
        self.ADMIN = ""
        self.GEMINI_KEY = ""
        self.ALLOW_LIST_FILENAME = ""
        self.USE_ALLOW_LIST = False
        self.CHAT_FILE = ""
        self.QUOTE_FILE = ""
        self.CHAT_GPT_MODEL = ""
        self.GEMINI_MODEL = ""
        self.logger = logger.getChild("config")
        self.load_config()
        self.verify_config()
        self.logger.info(f"The configuration '{self.filename}' is loaded.")

    def load_config(self):
        with open(self.filename, "r") as f:
            lines = f.readlines()
        # load the config, verify everything has a value.
        for line in lines:
            if line.startswith("openaikey"):
                self.CHAT_GPT_KEY = line[line.find("=") + 1 :].strip("\n").strip()
            if line.startswith("botkey"):
                self.BOT_KEY = line[line.find("=") + 1 :].strip("\n").strip()
            if line.startswith("admin"):
                self.ADMIN = line[line.find("=") + 1 :].strip("\n").strip()
            if line.startswith("googlegemini"):
                self.GEMINI_KEY = line[line.find("=") + 1 :].strip("\n").strip()
            if line.startswith("allowlistfilename"):
                self.ALLOW_LIST_FILENAME = (
                    line[line.find("=") + 1 :].strip("\n").strip()
                )
            if line.startswith("useallowlist"):
                readin = line[line.find("=") + 1 :].strip("\n").strip()
                if readin.lower().strip() == "true":
                    self.USE_ALLOW_LIST = True
                self.logger.info(f"Allow list is set to {self.USE_ALLOW_LIST}")
            if line.startswith("chatfile"):
                self.CHAT_FILE = line[line.find("=") + 1 :].strip("\n").strip()
            if line.startswith("quotefile"):
                self.QUOTE_FILE = line[line.find("=") + 1 :].strip("\n").strip()
            if line.startswith("openaimodel"):
                val = line[line.find("=") + 1 :].strip("\n").strip()
                self.CHAT_GPT_MODEL = "default" if val == "default" else val #empty means use whats in the code
            if line.startswith("googlecheminimodel"):
                val = line[line.find("=") + 1 :].strip("\n").strip()
                self.GEMINI_MODEL = "default" if val == "default" else val #empty means use whats in the code

    def verify_config(self):
        """
        Function checks for missing values in the configuration file properties and logs/raises
        an error if any are found.
        """
        for props, vals in self.__dict__.items():
            if vals == "":
                self.logger.error(f"Missing {props} in config file {self.filename}")
                raise Exception(f"Missing {props} in config file {self.filename}")
