from unittest.mock import MagicMock, patch

from app.core.llm import (
    chat_completion,
    extract_entities_topics,
    extract_keywords,
    generate_embeddings,
    generate_summary,
    get_chat_model,
    get_llm_client,
    merge_content,
)


class TestGetChatModel:
    def test_returns_none_when_no_api_key(self):
        """Test that get_chat_model returns None when no API key is set."""
        with patch("app.core.llm.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = ""
            result = get_chat_model()
            assert result is None

    def test_returns_model_when_api_key_set(self):
        """Test that get_chat_model returns a ChatOpenAI when API key is set."""
        with patch("app.core.llm.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = "test-key-123"
            with patch("app.core.llm.ChatOpenAI") as mock_chat:
                mock_chat.return_value = MagicMock()
                result = get_chat_model()
                assert result is not None
                mock_chat.assert_called_once_with(
                    model="gpt-4o-mini", api_key="test-key-123"
                )


class TestGetLLMClient:
    def test_returns_none_when_no_api_key(self):
        """Test that get_llm_client returns None when no API key is set."""
        with patch("app.core.llm.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = ""
            result = get_llm_client()
            assert result is None

    def test_returns_client_when_api_key_set(self):
        """Test that get_llm_client returns a ChatOpenAI when API key is set."""
        with patch("app.core.llm.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = "test-key-123"
            with patch("app.core.llm.ChatOpenAI") as mock_chat:
                mock_chat.return_value = MagicMock()
                result = get_llm_client()
                assert result is not None


class TestGenerateSummary:
    def test_returns_placeholder_without_api_key(self):
        """Test graceful handling when no API key is configured."""
        with patch("app.core.llm.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = ""
            result = generate_summary("Some text to summarize")
            assert "not available" in result.lower() or "no api key" in result.lower()

    def test_returns_summary_with_mocked_chain(self):
        """Test summary generation with mocked LangChain chain."""
        with patch("app.core.llm.get_chat_model") as mock_get_model:
            mock_model = MagicMock()
            mock_get_model.return_value = mock_model
            # Mock the chain invoke by mocking the pipe operator result
            mock_chain = MagicMock()
            mock_chain.invoke.return_value = "This is a test summary."
            with patch(
                "app.core.llm.ChatPromptTemplate"
            ) as mock_prompt_cls:
                mock_prompt = MagicMock()
                mock_prompt_cls.from_messages.return_value = mock_prompt
                mock_prompt.__or__ = MagicMock(return_value=MagicMock())
                mock_prompt.__or__.return_value.__or__ = MagicMock(
                    return_value=mock_chain
                )
                result = generate_summary("Some long text content to summarize.")
                assert result == "This is a test summary."

    def test_handles_exception_gracefully(self):
        """Test that exceptions are handled."""
        with patch("app.core.llm.get_chat_model") as mock_get_model:
            mock_model = MagicMock()
            mock_get_model.return_value = mock_model
            with patch(
                "app.core.llm.ChatPromptTemplate"
            ) as mock_prompt_cls:
                mock_prompt = MagicMock()
                mock_prompt_cls.from_messages.return_value = mock_prompt
                mock_prompt.__or__ = MagicMock(side_effect=Exception("API error"))
                result = generate_summary("Some text")
                assert "not available" in result.lower() or "failed" in result.lower()


class TestExtractKeywords:
    def test_returns_empty_list_without_api_key(self):
        """Test graceful handling when no API key is configured."""
        with patch("app.core.llm.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = ""
            result = extract_keywords("Some text with keywords")
            assert result == []

    def test_returns_keywords_with_mocked_chain(self):
        """Test keyword extraction with mocked LangChain chain."""
        with patch("app.core.llm.get_chat_model") as mock_get_model:
            mock_model = MagicMock()
            mock_get_model.return_value = mock_model
            mock_chain = MagicMock()
            mock_chain.invoke.return_value = "python, fastapi, testing"
            with patch(
                "app.core.llm.ChatPromptTemplate"
            ) as mock_prompt_cls:
                mock_prompt = MagicMock()
                mock_prompt_cls.from_messages.return_value = mock_prompt
                mock_prompt.__or__ = MagicMock(return_value=MagicMock())
                mock_prompt.__or__.return_value.__or__ = MagicMock(
                    return_value=mock_chain
                )
                result = extract_keywords("Text about python and fastapi testing.")
                assert result == ["python", "fastapi", "testing"]

    def test_handles_exception_gracefully(self):
        """Test that exceptions are handled."""
        with patch("app.core.llm.get_chat_model") as mock_get_model:
            mock_model = MagicMock()
            mock_get_model.return_value = mock_model
            with patch(
                "app.core.llm.ChatPromptTemplate"
            ) as mock_prompt_cls:
                mock_prompt = MagicMock()
                mock_prompt_cls.from_messages.return_value = mock_prompt
                mock_prompt.__or__ = MagicMock(side_effect=Exception("API error"))
                result = extract_keywords("Some text")
                assert result == []


class TestGenerateEmbeddings:
    def test_returns_zero_vectors_without_api_key(self):
        """Test graceful handling when no API key is configured."""
        with patch("app.core.llm.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = ""
            result = generate_embeddings(["text1", "text2"])
            assert len(result) == 2
            assert all(len(v) == 1536 for v in result)
            assert all(all(x == 0.0 for x in v) for v in result)

    def test_returns_embeddings_with_mocked_openai_embeddings(self):
        """Test embedding generation with mocked OpenAIEmbeddings."""
        with patch("app.core.llm.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = "test-key-123"
            with patch("app.core.llm.OpenAIEmbeddings") as mock_embeddings_cls:
                mock_embeddings = MagicMock()
                mock_embeddings.embed_documents.return_value = [
                    [0.1] * 1536,
                    [0.2] * 1536,
                ]
                mock_embeddings_cls.return_value = mock_embeddings
                result = generate_embeddings(["text1", "text2"])
                assert len(result) == 2
                assert result[0] == [0.1] * 1536
                assert result[1] == [0.2] * 1536
                mock_embeddings.embed_documents.assert_called_once_with(
                    ["text1", "text2"]
                )

    def test_handles_exception_gracefully(self):
        """Test that exceptions are handled."""
        with patch("app.core.llm.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = "test-key-123"
            with patch("app.core.llm.OpenAIEmbeddings") as mock_embeddings_cls:
                mock_embeddings_cls.return_value.embed_documents.side_effect = (
                    Exception("API error")
                )
                result = generate_embeddings(["text1"])
                assert len(result) == 1
                assert all(x == 0.0 for x in result[0])


class TestChatCompletion:
    def test_returns_error_message_without_api_key(self):
        """Test graceful handling when no API key is configured."""
        with patch("app.core.llm.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = ""
            result = chat_completion(
                messages=[{"role": "user", "content": "Hello"}],
                context="Some context",
            )
            assert "not available" in result.lower()

    def test_returns_answer_with_mocked_chain(self):
        """Test chat completion with mocked LangChain chain."""
        with patch("app.core.llm.get_chat_model") as mock_get_model:
            mock_model = MagicMock()
            mock_get_model.return_value = mock_model
            mock_chain = MagicMock()
            mock_chain.invoke.return_value = "The answer is 42."
            with patch(
                "app.core.llm.ChatPromptTemplate"
            ) as mock_prompt_cls:
                mock_prompt = MagicMock()
                mock_prompt_cls.from_messages.return_value = mock_prompt
                mock_prompt.__or__ = MagicMock(return_value=MagicMock())
                mock_prompt.__or__.return_value.__or__ = MagicMock(
                    return_value=mock_chain
                )
                result = chat_completion(
                    messages=[{"role": "user", "content": "What is the answer?"}],
                    context="The answer to everything is 42.",
                )
                assert result == "The answer is 42."

    def test_handles_exception_gracefully(self):
        """Test that exceptions are handled."""
        with patch("app.core.llm.get_chat_model") as mock_get_model:
            mock_model = MagicMock()
            mock_get_model.return_value = mock_model
            with patch(
                "app.core.llm.ChatPromptTemplate"
            ) as mock_prompt_cls:
                mock_prompt = MagicMock()
                mock_prompt_cls.from_messages.return_value = mock_prompt
                mock_prompt.__or__ = MagicMock(side_effect=Exception("API error"))
                result = chat_completion(
                    messages=[{"role": "user", "content": "Hello"}],
                    context="context",
                )
                assert "failed" in result.lower() or "error" in result.lower()


class TestExtractEntitiesTopics:
    def test_returns_empty_without_api_key(self):
        """Test graceful handling when no API key is configured."""
        with patch("app.core.llm.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = ""
            result = extract_entities_topics("Some text with entities")
            assert result == {"entities": [], "topics": []}

    def test_returns_entities_and_topics_with_mocked_chain(self):
        """Test entity/topic extraction with mocked chain."""
        with patch("app.core.llm.get_chat_model") as mock_get_model:
            mock_model = MagicMock()
            mock_get_model.return_value = mock_model
            mock_chain = MagicMock()
            mock_chain.invoke.return_value = (
                '{"entities": ["Python", "FastAPI"], "topics": ["Web Development"]}'
            )
            with patch(
                "app.core.llm.ChatPromptTemplate"
            ) as mock_prompt_cls:
                mock_prompt = MagicMock()
                mock_prompt_cls.from_messages.return_value = mock_prompt
                mock_prompt.__or__ = MagicMock(return_value=MagicMock())
                mock_prompt.__or__.return_value.__or__ = MagicMock(
                    return_value=mock_chain
                )
                result = extract_entities_topics("Python and FastAPI for web dev.")
                assert result == {
                    "entities": ["Python", "FastAPI"],
                    "topics": ["Web Development"],
                }

    def test_handles_invalid_json_gracefully(self):
        """Test graceful handling of invalid JSON response."""
        with patch("app.core.llm.get_chat_model") as mock_get_model:
            mock_model = MagicMock()
            mock_get_model.return_value = mock_model
            mock_chain = MagicMock()
            mock_chain.invoke.return_value = "not valid json"
            with patch(
                "app.core.llm.ChatPromptTemplate"
            ) as mock_prompt_cls:
                mock_prompt = MagicMock()
                mock_prompt_cls.from_messages.return_value = mock_prompt
                mock_prompt.__or__ = MagicMock(return_value=MagicMock())
                mock_prompt.__or__.return_value.__or__ = MagicMock(
                    return_value=mock_chain
                )
                result = extract_entities_topics("Some text")
                assert result == {"entities": [], "topics": []}


class TestMergeContent:
    def test_returns_concatenation_without_api_key(self):
        """Test fallback when no API key is configured."""
        with patch("app.core.llm.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = ""
            result = merge_content("existing content", "new info")
            assert "existing content" in result
            assert "new info" in result

    def test_returns_merged_content_with_mocked_chain(self):
        """Test content merging with mocked chain."""
        with patch("app.core.llm.get_chat_model") as mock_get_model:
            mock_model = MagicMock()
            mock_get_model.return_value = mock_model
            mock_chain = MagicMock()
            mock_chain.invoke.return_value = "# Merged\n\nCombined content here."
            with patch(
                "app.core.llm.ChatPromptTemplate"
            ) as mock_prompt_cls:
                mock_prompt = MagicMock()
                mock_prompt_cls.from_messages.return_value = mock_prompt
                mock_prompt.__or__ = MagicMock(return_value=MagicMock())
                mock_prompt.__or__.return_value.__or__ = MagicMock(
                    return_value=mock_chain
                )
                result = merge_content("existing", "new info")
                assert result == "# Merged\n\nCombined content here."

    def test_handles_exception_gracefully(self):
        """Test graceful handling of exceptions."""
        with patch("app.core.llm.get_chat_model") as mock_get_model:
            mock_model = MagicMock()
            mock_get_model.return_value = mock_model
            with patch(
                "app.core.llm.ChatPromptTemplate"
            ) as mock_prompt_cls:
                mock_prompt = MagicMock()
                mock_prompt_cls.from_messages.return_value = mock_prompt
                mock_prompt.__or__ = MagicMock(side_effect=Exception("API error"))
                result = merge_content("existing content", "new info")
                assert "existing content" in result
                assert "new info" in result
