import openai
import google.generativeai as genai
import logging

from app_config import BotConfiguration


class LLM_ACCESS:
    def __init__(self, config: BotConfiguration, logger: logging.Logger) -> None:
        self.logger = logger
        self.config = config

    def gpt_4(
        self, message="", prev_sub="", system_is="You are a helpful assistant.", temp=1
    ):
        openai.api_key = self.config.CHAT_GPT_KEY
        GPT_4_MODEL_NAME = "gpt-4-0125-preview"
        if message:
            try_counter = 0
            MAX_TRIES = 4
            while try_counter < MAX_TRIES:
                try:
                    response = openai.chat.completions.create(
                        # model="gpt-4",
                        model=GPT_4_MODEL_NAME,
                        # temperature=temp,
                        messages=[
                            {"role": "system", "content": system_is},
                            {"role": "assistant", "content": prev_sub},
                            {"role": "user", "content": message},
                        ],
                    )
                    self.logger.info(f"   * GPT responded with try {try_counter}")
                    return response.choices[0].message.content
                except Exception as e:
                    try_counter += 1
            # if we get here, throw an error:
            raise Exception("Failure while sending to ChatGPT")
        else:
            return "Sorry, but did you mean to say something?"

    def google_gemini(self, message: str):
        genai.configure(api_key=self.config.GEMINI_KEY)
        generation_config = {
            "temperature": 0.9,
            "top_p": 1,
            "top_k": 1,
            "max_output_tokens": 2048,
        }
        # https://ai.google.dev/docs/safety_setting_gemini
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        model = genai.GenerativeModel(
            model_name="gemini-1.0-pro",
            generation_config=generation_config,
            safety_settings=safety_settings,
        )
        response = model.generate_content(message)
        self.logger.info(f"   * Gemini responded")
        # TODO : This needs retry logic.
        return response.text

    def dall_E_3(self, message: str, size="1024x1024", quality="standard"):
        openai.api_key = self.config.CHAT_GPT_KEY
        if message and size in ["1024x1024", "1792x1024", "1024x1792"]:
            try:
                response = openai.images.generate(
                    model="dall-e-3",
                    prompt=message,
                    n=1,
                    size=size,
                    quality=quality,
                )
                return response.data[0].url
            except Exception as e:
                self.logger.error(f" Dall-E3 failed with {e}")
        return "Sorry but there's nothing to go by here."
