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
from typing import Annotated, Any
from pydantic import (
    BaseModel, 
    Field, 
    StringConstraints, 
    field_validator,
)

# SuggestedQuestion is a type alias to standardized the question
# strings.
# SuggestedQuestion is a string that will strip whitespaces, have
# at least 8 chars, and at most 180 chars.
SuggestedQuestion = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=8,
        max_length=180,
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
    