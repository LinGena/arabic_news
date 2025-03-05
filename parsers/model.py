import time
import json
from typing import Optional, Any, List
from llama_index.llms.bedrock import Bedrock
from llama_index.core.constants import (DEFAULT_TEMPERATURE,)
from llama_index.core.base.llms.types import MessageRole, LLMMetadata
from llama_index.core.types import BaseOutputParser, PydanticProgramMode
from llama_index.core.callbacks import CallbackManager
from llama_index.core.bridge.pydantic import Field
from llama_index.llms.bedrock.utils import *
import os
from parsers.functions import Functions


CHAT_ONLY_MODELS['amazon.nova-lite-v1:0'] = 100000 
CHAT_ONLY_MODELS['amazon.nova-pro-v1:0'] = 100000 
CHAT_ONLY_MODELS['amazon.nova-canvas-v1:0'] = 100000 
CHAT_ONLY_MODELS['amazon.nova-micro-v1:0'] = 100000 

def _nova_messages_to_prompt(messages: Sequence[ChatMessage]) -> List[dict]:
    nova_messages = []
    system_prompt = []
    for message in messages:
        if message.role == MessageRole.SYSTEM:
            system_prompt.append({"text": message.content})
        else:
            nova_messages.append({"role": message.role, "content": [{"text": message.content}]})
    if not system_prompt:
        system_prompt = [{"text": ""}]
    return nova_messages, system_prompt


class AmazonNovaProvider(Provider):
    max_tokens_key = "max_new_tokens"

    def __init__(self) -> None:
        self.messages_to_prompt = _nova_messages_to_prompt
        self.completion_to_prompt = completion_to_anthopic_prompt

    def get_text_from_response(self, response: dict) -> str:
        return response["output"]["message"]['content'][0]['text']

    def get_text_from_stream_response(self, response: dict) -> str:
        return response["outputText"]

    def get_request_body(self, prompt: str, inference_parameters: dict) -> dict:
        return {
            "schemaVersion": "messages-v1",
            "messages": prompt[0],
            "system": prompt[1],
            "inferenceConfig": {
                "max_new_tokens": inference_parameters.get(self.max_tokens_key), 
                "top_p": 0.9, 
                "top_k": 20, 
                "temperature": inference_parameters.get('temperature')},
        }
    
PROVIDERS = {
    "amazon.nova": AmazonNovaProvider(),
    "amazon": AmazonProvider(),
    "ai21": Ai21Provider(),
    "anthropic": AnthropicProvider(),
    "cohere": CohereProvider(),
    "meta": MetaProvider(),
    "mistral": MistralProvider(),
}

def get_provider(model: str) -> Provider:
    if model.startswith('eu.') or model.startswith('us.'):
        provider_name = model.split(".")[1]
    elif "nova" in model:
        provider_name = 'amazon.nova'
    else:
        provider_name = model.split(".")[0]
    if provider_name not in PROVIDERS:
        raise ValueError(f"Provider {provider_name} for model {model} is not supported")
    return PROVIDERS[provider_name]

class AWSBoto(Bedrock):

    requests: List[dict] = Field(
        default=[],
        description="Chat history",
    )
    attempt: int = Field(
        default=0,
        description="Current attempt of reqeusts",
    )
    model_id: Any = Field(
        default=None,
        description="llm model",
    )

    message: Any = Field(
        default=None,
        description="llm response",
    )
    
    def __init__(self,
                 model: str,
                 temperature: Optional[float] = DEFAULT_TEMPERATURE,
                 max_tokens: Optional[int] = 512,
                 context_size: Optional[int] = None,
                 profile_name: Optional[str] = None,
                 aws_access_key_id: Optional[str] = os.getenv('AWS_ACCESS_KEY_ID'),
                 aws_secret_access_key: Optional[str] = os.getenv('AWS_SECRET_ACCESS_KEY'),
                 aws_session_token: Optional[str] = None,
                 region_name: Optional[str] = os.getenv('AWS_DEFAULT_REGION'),
                 botocore_session: Optional[Any] = None,
                 client: Optional[Any] = None,
                 timeout: Optional[float] = 60.0,
                 max_retries: Optional[int] = 10,
                 botocore_config: Optional[Any] = None,
                 additional_kwargs: Optional[Dict[str, Any]] = None,
                 callback_manager: Optional[CallbackManager] = None,
                 system_prompt: Optional[str] = None,
                 messages_to_prompt: Optional[Callable[[Sequence[ChatMessage]], str]] = None,
                 completion_to_prompt: Optional[Callable[[str], str]] = None,
                 pydantic_program_mode: PydanticProgramMode = PydanticProgramMode.DEFAULT,
                 output_parser: Optional[BaseOutputParser] = None,
                 **kwargs: Any,):
        super().__init__(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            context_size=context_size,
            profile_name=profile_name,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token,
            region_name=region_name,
            botocore_session=botocore_session,
            client=client,
            timeout=timeout,
            max_retries=max_retries,
            botocore_config=botocore_config,
            additional_kwargs=additional_kwargs,
            callback_manager=callback_manager,
            system_prompt=system_prompt,
            messages_to_prompt=messages_to_prompt,
            completion_to_prompt=completion_to_prompt,
            pydantic_program_mode=pydantic_program_mode,
            output_parser=output_parser,
            **kwargs
        )
        self._provider = get_provider(model)
        self.messages_to_prompt = messages_to_prompt or self._provider.messages_to_prompt
        self.completion_to_prompt = (
            completion_to_prompt or self._provider.completion_to_prompt
        )
        self.message = None
        self.requests = []
        if system_prompt:
            self.requests.append(ChatMessage.from_str(content=system_prompt, role='system'))
        self.attempt = 0
    
    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(
            context_window=self.context_size,
            num_output=self.max_tokens,
            is_chat_model=self.model in CHAT_ONLY_MODELS,
            model_name=self.model,
        )

    def clear(self):
        self.requests = []
    
    def send(self, text):
        message = ChatMessage.from_str(content=text, role='user')
        self.add_message(message)
        self._request()

    def as_chat(self, query):
        self.send(query)
        return self.message

    def _request(self, attempt=4):
        try:
            chat_response = self.chat(self.requests)
            self.message = chat_response.message.content
            self.add_message(chat_response.message)
        except Exception as err:
            attempt = attempt - 1
            if "Try your request again" in str(err) and attempt >= 0:
                time.sleep(30)
                self._request(attempt)
            else: raise

    def add_message(self, message):
        self.requests.append(message)


class CheckNewsModel(Functions):
    def __init__(self):
        super().__init__()
        self.llm = AWSBoto(os.getenv("AWS_MODEL"), 
                           context_size=236000,
                           region_name='us-east-1',
                           )

    def check_aws_bedrock(self, speaker: str, news: dict, lang: str = 'ar') -> bool:
        try:
            article = f"{news.get('news_title')} \n{news.get('news_body')}"
            prompt = self.get_prompt(speaker, article, lang)
            response = self.llm.as_chat(prompt)
            self.llm.clear()
            response = str(response).strip().lower()
            print(response)
            response_json = json.loads(response)
            return response_json
        except Exception as ex:
            self.logger.error(ex)
        return {'is_about':False, 'explanation':'error'}
        
    def get_prompt(self, speaker: str, article: str, lang: str = 'ar') -> str:
        if lang == 'ar':
            search_keywords = ', '.join(self.get_search_terms())
        else:
            search_keywords = ', '.join(self.get_search_terms(return_value=True))
        prompt = f"""
Analyze the Arabic news article and determine if {speaker} personally made statements about the Israeli-Palestinian conflict.

Instructions:
- Return "True" if {speaker} made at least one relevant statement regarding the conflict.
- Return "False" if the article only mentions {speaker} but does not contain his direct statements on this topic.
- Ignore mentions of the conflict if they are not statements made by {speaker}.
- Ignore mentions of unrelated parties (e.g., Foreign Ministry employees or other government officials).
- Ensure that statements attributed to {speaker} are directly related to {search_keywords}.

Article Data: 
{article}
Output Format (IMPORTANT):
Please output your final answer **in valid JSON** with exactly two fields:
1. "is_about": a boolean (true or false),
2. "explanation": xplanation why this is true or false in English, if you need to include words from other languages for explanation - you can. Please explain step by step why this is true or false 
"""
        
        return prompt
    

