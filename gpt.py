import openai
import google.generativeai as genai
import logging

from app_config import BotConfiguration


class LLM_ACCESS:
    def __init__(self, config: BotConfiguration, logger: logging.Logger) -> None:
        self.logger = logger
        self.config = config

    def gpt_4(
        self, message="", prev_sub="", system_is="You are a helpful assistant.", 
        temp=1, openAI_model="gpt-4o"
    ):
        openai.api_key = self.config.CHAT_GPT_KEY
        if message:
            try_counter = 0
            MAX_TRIES = 4
            while try_counter < MAX_TRIES:
                try:
                    response = openai.chat.completions.create(
                        # model="gpt-4",
                        model=openAI_model,
                        # temperature=temp,
                        messages=[
                            #{"role": "system", "content": system_is}, # TEMP DISABLED FOR USING PREVIEW MODELS
                            {"role": "assistant", "content": prev_sub},
                            {"role": "user", "content": message},
                        ],
                    )
                    self.logger.info(f"   * GPT responded with try {try_counter}")
                    return response.choices[0].message.content
                except Exception as e:
                    self.logger.error(f" GPT failed with {e} on try {try_counter}, using model {openAI_model}")
                    try_counter += 1
            # if we get here, throw an error:
            raise Exception("Failure while sending to ChatGPT: ")
        else:
            return "Sorry, but did you mean to say something?"

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
    
    def get_openai_models(self) -> list[str]:
        openai.api_key = self.config.CHAT_GPT_KEY
        res = openai.models.list()
        model_names = [model.id for model in res.data]
        return model_names
        
    def google_gemini(self, message: str, model_to_use = "gemini-1.5-pro-latest"):
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
            model_name=model_to_use,
            generation_config=generation_config,
            safety_settings=safety_settings,
        )
        response = model.generate_content(message)
        self.logger.info(f"   * Gemini responded")
        # TODO : This needs retry logic.
        return response.text

    def get_gemini_models(self) -> list[str]:
        # gets the models from Gemini API if you decide to use something new.
        genai.configure(api_key=self.config.GEMINI_KEY)
        models = genai.list_models()
        outlist= []
        for model in models:
            outlist.append(str(model.name).split("/")[1])
        return(outlist)
            