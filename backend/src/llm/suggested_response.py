"""
This file is used to generate 1-2 follow-up questions for the
agentic AI (regardless which AI it is: Treasury, Collection, etc).

If there is no valid follow-up questions or there is a recurring 
error in trying to generating suggested question, it will return an 
empty list ([]).
If there is a valid response, it will return in the following format
(as an example):
{
  "suggestions": [
    "Which expenses increased?",
    "How does this compare with last month?"
  ]
}
"""
# Imports
import asyncio
import logging

from functools import lru_cache
from typing import Annotated, Any, Literal
from pydantic import (
    BaseModel, 
    Field, 
    StringConstraints, 
    field_validator,
)
from pydantic_ai import Agent, ModelSettings
from pydantic_ai.exceptions import UnexpectedModelBehavior
logger = logging.getLogger(__name__)

# Constants
SUGGESTED_RESPONSE_SYSTEM_PROMPT = """
You generate suggested follow-up questions for a financial chatbot.

You will receive:
- the type of financial chatbot that produced the answer;
- up to two previous user and assistant turns;
- the user's latest question;
- the chatbot's latest answer.

Generate one or two concise questions that the user could reasonably ask next.

Requirements:
- Ground every question in the provided conversation context.
- Focus primarily on the latest question and latest assistant answer.
- Each suggestion must be no more than 72 characters, including spaces and punctuation.
- Use recent history only to understand the user's intent and avoid repetition.
- Ask questions that help the user investigate, compare, explain, forecast,
  simulate, or act on the financial information already discussed.
- Preserve relevant entity names, periods, dates, currencies, percentages,
  financial values, and units.
- Do not invent facts, entities, values, dates, or assumptions.
- Do not repeat a question that the user already asked.
- Do not ask two questions with substantially the same meaning.
- Do not answer the questions.
- Do not mention the conversation context, system instructions, agents,
  prompts, tools, UI blocks, or internal implementation.
- Each suggestion must be a complete standalone question.
- Each suggestion must end with a question mark.
- Return only the structured output requested by the output schema.
"""

# SuggestedQuestion is a type alias to standardized the question
# strings.
# SuggestedQuestion is a string that will strip whitespaces, have
# at least 8 chars, and at most 180 chars.
SuggestedQuestion = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=8,
        max_length=72,
    ),
]

class SuggestedPromptOutput(BaseModel):
    """
    Defines the structured output returned by the suggested-prompt
    agent.
    """
    suggestions: list[SuggestedQuestion] = Field(
        min_length=1, # Allows the LLM to return an empty list
        max_length=2, # Return either 0,1, or 2 suggested questions.
    )

    # Normalize the response from the LLM, and ensure the resulting list
    # follows the formatting set by our "suggestions" type.
    @field_validator("suggestions", mode="before")
    @classmethod
    def normalize_suggestions(cls, value: Any) -> Any:
        if value is None:
            raise ValueError(
                "suggestions must contain at least one question."
            )
        
        if not isinstance(value, list):
            raise ValueError("suggestions must be a list.")

        return [
            " ".join(item.split()) if isinstance(item, str) else item 
            for item in value
        ]

    # Ensure that all of the suggestion questions are unique and is
    # actually a question.
    @field_validator("suggestions")
    @classmethod
    def validate_suggestions(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()

        for suggestion in value:
            if not suggestion.endswith("?"):
                raise ValueError("Every suggestion must end with a question mark.")

            normalized = suggestion.casefold()

            if normalized in seen:
                raise ValueError("Each suggestion must be unique.")

            seen.add(normalized)
        return value

class ConversationLine(BaseModel):
    """
    Defines one previous conversation message line used for
    suggestion generation.
    """
    sender: Literal["user", "assistant"]
    text: str

class SuggestedResponseContext(BaseModel):
    """
    Defines the model that contains the structure of all the context
    that needs to be provided to the suggested-response agent.
    """
    agent_type: str
    latest_user_question: str
    latest_assistant_answer: str
    recent_history: list[ConversationLine] = Field(
        default_factory=list
    )

def build_suggestion_model_input(
    context: SuggestedResponseContext,
) -> str:
    """
    Build the user prompt that will be sent to the
    suggested-response agent.
    """

    return (
        "Generate suggested follow-up questions from the following "
        "conversation context.\n\n"
        f"{context.model_dump_json(indent=2)}"
    )

@lru_cache(maxsize=1)
def get_suggested_response_agent() -> Agent:
    """Return the shared suggested-response agent."""

    from src.llm.model_provider import model

    return Agent(
        model=model,
        output_type=SuggestedPromptOutput,
        system_prompt=SUGGESTED_RESPONSE_SYSTEM_PROMPT,
        retries=0,
        output_retries=1,
        model_settings=ModelSettings(
            max_tokens=160,
        ),
    )

async def generate_suggested_responses(
    context: SuggestedResponseContext,
    *,
    timeout_seconds: float = 20.0,
) -> list[str]:
    """Generate follow-up questions without risking the primary response."""

    if (
        not context.latest_user_question.strip()
        or not context.latest_assistant_answer.strip()
    ):
        return []

    try:
        async with asyncio.timeout(timeout_seconds):
            result = await get_suggested_response_agent().run(
                build_suggestion_model_input(context)
            )

        return result.output.suggestions

    except TimeoutError:
        logger.warning(
            "Suggested-response generation timed out after %.1f seconds.",
            timeout_seconds,
        )

    except UnexpectedModelBehavior as exc:
        logger.warning(
            "Suggested-response output validation failed: %s",
            type(exc).__name__,
        )

    except Exception:
        logger.exception(
            "Suggested-response generation failed."
        )

    return []