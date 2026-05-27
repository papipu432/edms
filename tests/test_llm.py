from unittest.mock import MagicMock, patch

from app.core.llm import (
    chat_completion,
    extract_keywords,
    generate_embeddings,
    generate_summary,
    get_llm_client,
)


class TestGetLLMClient:
    def test_returns_none_when_no_api_key(self):
        """Test that get_llm_client returns None when no API key is set."""
        with patch("app.core.llm.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = ""
            result = get_llm_client()
            assert result is None

    def test_returns_client_when_api_key_set(self):
        """Test that get_llm_client returns an OpenAI client when API key is set."""
        with patch("app.core.llm.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = "test-key-123"
            with patch("app.core.llm.OpenAI") as mock_openai:
                mock_openai.return_value = MagicMock()
                result = get_llm_client()
                assert result is not None
                mock_openai.assert_called_once_with(api_key="test-key-123")


class TestGenerateSummary:
    def test_returns_placeholder_without_api_key(self):
        """Test graceful handling when no API key is configured."""
        with patch("app.core.llm.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = ""
            result = generate_summary("Some text to summarize")
            assert "not available" in result.lower() or "no api key" in result.lower()

    def test_returns_summary_with_mocked_openai(self):
        """Test summary generation with mocked OpenAI response."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "This is a test summary."
        mock_client.chat.completions.create.return_value = mock_response

        with patch("app.core.llm.get_llm_client", return_value=mock_client):
            result = generate_summary("Some long text content to summarize.")
            assert result == "This is a test summary."
            mock_client.chat.completions.create.assert_called_once()

    def test_handles_exception_gracefully(self):
        """Test that exceptions from OpenAI are handled."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API error")

        with patch("app.core.llm.get_llm_client", return_value=mock_client):
            result = generate_summary("Some text")
            assert "not available" in result.lower() or "failed" in result.lower()


class TestExtractKeywords:
    def test_returns_empty_list_without_api_key(self):
        """Test graceful handling when no API key is configured."""
        with patch("app.core.llm.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = ""
            result = extract_keywords("Some text with keywords")
            assert result == []

    def test_returns_keywords_with_mocked_openai(self):
        """Test keyword extraction with mocked OpenAI response."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "python, fastapi, testing"
        mock_client.chat.completions.create.return_value = mock_response

        with patch("app.core.llm.get_llm_client", return_value=mock_client):
            result = extract_keywords("Text about python and fastapi testing.")
            assert result == ["python", "fastapi", "testing"]
            mock_client.chat.completions.create.assert_called_once()

    def test_handles_exception_gracefully(self):
        """Test that exceptions from OpenAI are handled."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API error")

        with patch("app.core.llm.get_llm_client", return_value=mock_client):
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

    def test_returns_embeddings_with_mocked_openai(self):
        """Test embedding generation with mocked OpenAI response."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_item1 = MagicMock()
        mock_item1.embedding = [0.1] * 1536
        mock_item2 = MagicMock()
        mock_item2.embedding = [0.2] * 1536
        mock_response.data = [mock_item1, mock_item2]
        mock_client.embeddings.create.return_value = mock_response

        with patch("app.core.llm.get_llm_client", return_value=mock_client):
            result = generate_embeddings(["text1", "text2"])
            assert len(result) == 2
            assert result[0] == [0.1] * 1536
            assert result[1] == [0.2] * 1536
            mock_client.embeddings.create.assert_called_once()

    def test_handles_exception_gracefully(self):
        """Test that exceptions from OpenAI are handled."""
        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = Exception("API error")

        with patch("app.core.llm.get_llm_client", return_value=mock_client):
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

    def test_returns_answer_with_mocked_openai(self):
        """Test chat completion with mocked OpenAI response."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "The answer is 42."
        mock_client.chat.completions.create.return_value = mock_response

        with patch("app.core.llm.get_llm_client", return_value=mock_client):
            result = chat_completion(
                messages=[{"role": "user", "content": "What is the answer?"}],
                context="The answer to everything is 42.",
            )
            assert result == "The answer is 42."
            mock_client.chat.completions.create.assert_called_once()

    def test_handles_exception_gracefully(self):
        """Test that exceptions from OpenAI are handled."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API error")

        with patch("app.core.llm.get_llm_client", return_value=mock_client):
            result = chat_completion(
                messages=[{"role": "user", "content": "Hello"}],
                context="context",
            )
            assert "failed" in result.lower() or "error" in result.lower()
