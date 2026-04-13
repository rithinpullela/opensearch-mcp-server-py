# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field, model_validator
from pydantic_core import PydanticCustomError
from typing import Literal

from tools.tool_params import baseToolArgs


class MemoryType(str, Enum):
    """Specifies the different types of agentic memory."""

    sessions = 'sessions'
    working = 'working'
    long_term = 'long-term'
    history = 'history'


class PayloadType(str, Enum):
    """Specifies the type of payload being added to agentic memory."""

    conversational = 'conversational'
    data = 'data'


class MessageContentItem(BaseModel):
    """Schema for the content part of a message."""

    text: str = Field(..., description='The text content of the message.')
    content_type: str = Field(
        ..., description="The type of the content (e.g., 'text').", alias='type'
    )


class MessageItem(BaseModel):
    """Schema for a single message in the messages field."""

    role: Optional[str] = Field(
        None, description="The role of the entity (e.g., 'user', 'assistant')."
    )
    content: List[MessageContentItem] = Field(
        ..., description='A list of content items for this message.'
    )


class BaseAgenticMemoryContainerArgs(baseToolArgs):
    """Base arguments for tools operating on an Agentic Memory Container."""

    memory_container_id: str = Field(..., description='The ID of the memory container.')


class CreateAgenticMemorySessionArgs(BaseAgenticMemoryContainerArgs):
    """Arguments for creating a new session in an agentic memory container."""

    session_id: Optional[str] = Field(
        default=None,
        description='A custom session ID. If not provided, a random ID is generated.',
    )
    summary: Optional[str] = Field(default=None, description='A session summary or description.')
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description='Additional metadata for the session provided as key-value pairs.',
    )
    namespace: Optional[Dict[str, str]] = Field(
        default=None, description='Namespace information for organizing the session.'
    )

    class Config:
        json_schema_extra = {
            'examples': [
                {
                    'memory_container_id': 'SdjmmpgBOh0h20Y9kWuN',
                    'session_id': 'abc123',
                    'metadata': {'key1': 'value1'},
                },
            ]
        }


_ERR_MESSAGES_REQUIRED = 'messages_required'
_ERR_FIELD_PROHIBITED = 'field_prohibited'
_ERR_STRUCTURED_DATA_REQUIRED = 'structured_data_required'
_ERR_MISSING_CONTENT_FIELD = 'missing_content_field'
_ERR_FIELD_NOT_ALLOWED = 'field_not_allowed'
_ERR_MISSING_WORKING_FIELD = 'missing_working_field'
_ERR_MISSING_LONG_TERM_FIELD = 'missing_long_term_field'


class AddAgenticMemoriesArgs(BaseAgenticMemoryContainerArgs):
    """Arguments for adding memories to an agentic memory container."""

    messages: Optional[List[MessageItem]] = Field(
        default=None, description='A list of messages for a conversational payload.'
    )
    structured_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description='Structured data content for data memory. Required when payload_type is data.',
    )
    binary_data: Optional[str] = Field(
        default=None,
        description='Binary data content encoded as a Base64 string for binary payloads.',
    )
    payload_type: PayloadType = Field(
        ..., description='The type of payload. Valid values are conversational or data.'
    )
    namespace: Optional[Dict[str, str]] = Field(
        default=None, description='The namespace context for organizing memories.'
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None, description='Additional metadata for the memory.'
    )
    tags: Optional[Dict[str, Any]] = Field(
        default=None, description='Tags for categorizing and organizing memories.'
    )
    infer: Optional[bool] = Field(
        default=False,
        description='Whether to use a large language model (LLM) to extract key information.',
    )

    @model_validator(mode='after')
    def validate_payload_requirements(self) -> 'AddAgenticMemoriesArgs':
        """Validate that the correct fields are provided based on payload_type."""
        set_fields = self.model_fields_set

        if self.payload_type == PayloadType.conversational:
            if 'messages' not in set_fields:
                raise PydanticCustomError(
                    _ERR_MESSAGES_REQUIRED,
                    "'messages' field is required when payload_type is 'conversational'",
                )
            if 'structured_data' in set_fields:
                raise PydanticCustomError(
                    _ERR_FIELD_PROHIBITED,
                    "'structured_data' should not be provided when payload_type is 'conversational'",
                    {'field_name': 'structured_data'},
                )
        elif self.payload_type == PayloadType.data:
            if 'structured_data' not in set_fields:
                raise PydanticCustomError(
                    _ERR_STRUCTURED_DATA_REQUIRED,
                    "'structured_data' field is required when payload_type is 'data'",
                )
            if 'messages' in set_fields:
                raise PydanticCustomError(
                    _ERR_FIELD_PROHIBITED,
                    "'messages' should not be provided when payload_type is 'data'",
                    {'field_name': 'messages'},
                )

        content_fields = {'messages', 'structured_data', 'binary_data'}
        if not any(field in set_fields for field in content_fields):
            raise PydanticCustomError(
                _ERR_MISSING_CONTENT_FIELD,
                'At least one content field (messages, structured_data, or binary_data) must be provided',
            )

        return self

    class Config:
        json_schema_extra = {
            'examples': [
                {
                    'memory_container_id': 'SdjmmpgBOh0h20Y9kWuN',
                    'messages': [
                        {
                            'role': 'user',
                            'content': [
                                {'text': "I'm Bob, I really like swimming.", 'type': 'text'}
                            ],
                        },
                        {
                            'role': 'assistant',
                            'content': [
                                {'text': 'Cool, nice. Hope you enjoy your life.', 'type': 'text'}
                            ],
                        },
                    ],
                    'namespace': {'user_id': 'bob'},
                    'infer': True,
                    'payload_type': 'conversational',
                },
            ]
        }


class GetAgenticMemoryArgs(BaseAgenticMemoryContainerArgs):
    """Arguments for retrieving a specific agentic memory by its type and ID."""

    memory_type: MemoryType = Field(
        ...,
        alias='type',
        description='The memory type. Valid values are sessions, working, long-term, and history.',
    )
    id: str = Field(..., description='The ID of the memory to retrieve.')

    class Config:
        json_schema_extra = {
            'examples': [
                {
                    'memory_container_id': 'HudqiJkB1SltqOcZusVU',
                    'type': 'working',
                    'id': 'XyEuiJkBeh2gPPwzjYWM',
                },
            ]
        }


class UpdateAgenticMemoryArgs(BaseAgenticMemoryContainerArgs):
    """Arguments for updating a specific agentic memory by its type and ID."""

    _SESSION_ONLY_FIELDS: Set[str] = {'summary', 'agents', 'additional_info'}
    _WORKING_ONLY_FIELDS: Set[str] = {'messages', 'structured_data', 'binary_data'}
    _LONG_TERM_ONLY_FIELDS: Set[str] = {'memory'}
    _UPDATABLE_WORKING_FIELDS: Set[str] = {
        'messages',
        'structured_data',
        'binary_data',
        'tags',
        'metadata',
    }
    _UPDATABLE_LONG_TERM_FIELDS: Set[str] = {'memory', 'tags', 'metadata'}

    memory_type: Literal[MemoryType.sessions, MemoryType.working, MemoryType.long_term] = Field(
        ...,
        alias='type',
        description='The memory type. Valid values are sessions, working, and long-term. History memory cannot be updated.',
    )
    id: str = Field(..., description='The ID of the memory to update.')
    summary: Optional[str] = Field(default=None, description='The summary of the session.')
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description='Additional metadata for the memory.',
    )
    agents: Optional[Dict[str, Any]] = Field(
        default=None, description='Additional information about the agents.'
    )
    additional_info: Optional[Dict[str, Any]] = Field(
        default=None, description='Additional metadata to associate with the session.'
    )
    messages: Optional[List[MessageItem]] = Field(
        default=None,
        description='Updated conversation messages (for conversation type).',
    )
    structured_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description='Updated structured data content (for data memory payloads).',
    )
    binary_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description='Updated binary data content (for data memory payloads).',
    )
    tags: Optional[Dict[str, Any]] = Field(
        default=None, description='Updated tags for categorization.'
    )
    memory: Optional[str] = Field(default=None, description='The updated memory content.')

    @model_validator(mode='after')
    def validate_memory_type_fields(self) -> 'UpdateAgenticMemoryArgs':
        """Validate that fields match the specified memory_type and minimum requirements."""
        set_fields = self.model_fields_set

        def _raise_not_allowed_error(field_name: str, memory_type: str):
            raise PydanticCustomError(
                _ERR_FIELD_NOT_ALLOWED,
                "Field '{field_name}' should not be provided when updating {memory_type} memory",
                {'field_name': field_name, 'memory_type': memory_type},
            )

        if self.memory_type == MemoryType.sessions:
            disallowed_fields = self._WORKING_ONLY_FIELDS | self._LONG_TERM_ONLY_FIELDS
            for field in disallowed_fields:
                if field in set_fields:
                    _raise_not_allowed_error(field, MemoryType.sessions)

        elif self.memory_type == MemoryType.working:
            disallowed_fields = self._SESSION_ONLY_FIELDS | self._LONG_TERM_ONLY_FIELDS
            for field in disallowed_fields:
                if field in set_fields:
                    _raise_not_allowed_error(field, MemoryType.working)

            if not any(field in set_fields for field in self._UPDATABLE_WORKING_FIELDS):
                raise PydanticCustomError(
                    _ERR_MISSING_WORKING_FIELD,
                    'At least one field ({fields}) must be provided for updating working memory',
                    {'fields': ', '.join(self._UPDATABLE_WORKING_FIELDS)},
                )

        elif self.memory_type == MemoryType.long_term:
            disallowed_fields = self._SESSION_ONLY_FIELDS | self._WORKING_ONLY_FIELDS
            for field in disallowed_fields:
                if field in set_fields:
                    _raise_not_allowed_error(field, MemoryType.long_term)

            if not any(field in set_fields for field in self._UPDATABLE_LONG_TERM_FIELDS):
                raise PydanticCustomError(
                    _ERR_MISSING_LONG_TERM_FIELD,
                    'At least one field ({fields}) must be provided for updating long-term memory',
                    {'fields': ', '.join(self._UPDATABLE_LONG_TERM_FIELDS)},
                )

        return self

    class Config:
        json_schema_extra = {
            'examples': [
                {
                    'memory_container_id': 'HudqiJkB1SltqOcZusVU',
                    'type': 'sessions',
                    'id': 'N2CDipkB2Mtr6INFFcX8',
                    'additional_info': {'key1': 'value1'},
                },
                {
                    'memory_container_id': 'HudqiJkB1SltqOcZusVU',
                    'type': 'working',
                    'id': 'XyEuiJkBeh2gPPwzjYWM',
                    'tags': {'topic': 'updated_topic', 'priority': 'high'},
                },
                {
                    'memory_container_id': 'HudqiJkB1SltqOcZusVU',
                    'type': 'long-term',
                    'id': 'DcxjTpkBvwXRq366C1Zz',
                    'memory': "User's name is Bob Smith",
                    'tags': {'topic': 'personal info'},
                },
            ]
        }


class DeleteAgenticMemoryByIDArgs(BaseAgenticMemoryContainerArgs):
    """Arguments for deleting a specific agentic memory by its type and ID."""

    memory_type: MemoryType = Field(
        ...,
        alias='type',
        description='The type of memory to delete. Valid values are sessions, working, long-term, and history.',
    )
    id: str = Field(..., description='The ID of the specific memory to delete.')

    class Config:
        json_schema_extra = {
            'examples': [
                {
                    'memory_container_id': 'HudqiJkB1SltqOcZusVU',
                    'type': 'working',
                    'id': 'XyEuiJkBeh2gPPwzjYWM',
                },
            ]
        }


class DeleteAgenticMemoryByQueryArgs(BaseAgenticMemoryContainerArgs):
    """Arguments for deleting agentic memories by query."""

    memory_type: MemoryType = Field(
        ...,
        alias='type',
        description='The type of memory to delete. Valid values are sessions, working, long-term, and history.',
    )
    query: Dict[str, Any] = Field(
        ...,
        description='The query to match the memories you want to delete. Must be a valid OpenSearch query DSL object.',
    )

    class Config:
        json_schema_extra = {
            'examples': [
                {
                    'memory_container_id': 'HudqiJkB1SltqOcZusVU',
                    'type': 'working',
                    'query': {'match': {'owner_id': 'admin'}},
                },
            ]
        }


class SearchAgenticMemoryArgs(BaseAgenticMemoryContainerArgs):
    """Arguments for searching memories of a specific type within an agentic memory container."""

    memory_type: MemoryType = Field(
        ...,
        alias='type',
        description='The memory type. Valid values are sessions, working, long-term, and history.',
    )
    query: Dict[str, Any] = Field(..., description='The search query using OpenSearch query DSL.')
    sort: Optional[List[Dict[str, Any]]] = Field(
        default=None, description='Sort specification for the search results.'
    )

    class Config:
        json_schema_extra = {
            'examples': [
                {
                    'memory_container_id': 'HudqiJkB1SltqOcZusVU',
                    'type': 'sessions',
                    'query': {'match_all': {}},
                    'sort': [{'created_time': {'order': 'desc'}}],
                },
            ]
        }
