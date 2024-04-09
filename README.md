# Telegram Chatbot with GPT / Gemini

Telegram ChatBot to use with OpenAI's API / Google Gemini.  Designed to work with both image generation and interaction with ChatGPT/Gemini via Telegram.  Just set up this bot, plug in the API key (OpenAI), Gemini(Google), and Botfather key (telegram) then start chatting with your bot or invite it to a  chat.  The user's chat is kept in context with chat-GPT (History of 1 for now)/Gemini and the bot is compatible with ChatGPT 4 / Gemini 1.5 .  

---

### Steps to get going!
__NOTE:__ These were the testing conditions I used, which means i know this works.  Anyone who wants to use this under other conditions may do so and even contribute for better compatibility.

* Python 3.10 +
* Ubuntu Server instance (Tested with 4GB ram, 8Gb disk, 2 Proccessors)
  * Sudo access and proper permissions to read/write files where the bot is running for the bot as well.
* Network connection
* Gemini API Key
* Open AI API Key
* Telegram Bot Key

You'll need to copy the sample_of_keys.txt file to the same directory you're running the telegram chat bot and follow the directions in the file.  All REQUIRED values must be filled in.

---

### Features not yet working
No database information is stored or read yet. (pending)  The intention is to have the user information consistent with the chatbot up to the last **X** messages.  This isn't integrated yet.  There are also planned controls of how this works.


### Admin stuff
Admins have some control.  For now, that control is for one person.  Admins can do things like set up an allow-list (partially implemented) and enable allow-listing to be used.  In addition, you can use commands like /admin which will give you a list of admin commands where other things might be handy such as /sys.# Tgram
