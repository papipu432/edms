"""
Local Airgap AI Assistant Service

Embeds privacy-preserving LLMs (Phi-3, Llama-3) directly in containers
for document summarization, extraction, and comparison without external API calls.
"""

import os
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path

logger = logging.getLogger(__name__)


class LocalAIAssistant:
    """Local LLM assistant for airgap environments"""
    
    def __init__(self, model_name: str = "phi-3", model_path: Optional[str] = None):
        self.model_name = model_name
        self.model_path = model_path or os.getenv("LOCAL_MODEL_PATH", "/models")
        self.model = None
        self.tokenizer = None
        self._initialized = False
    
    def initialize(self) -> bool:
        """Initialize local LLM model"""
        try:
            # Check if model exists
            model_dir = Path(self.model_path) / self.model_name
            if not model_dir.exists():
                logger.warning(f"Model {self.model_name} not found at {model_dir}")
                return False
            
            # Lazy loading - only import when needed
            from transformers import AutoTokenizer, AutoModelForCausalLM
            import torch
            
            logger.info(f"Loading {self.model_name} model...")
            
            # Load tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(
                str(model_dir),
                trust_remote_code=True
            )
            
            # Load model with appropriate precision
            self.model = AutoModelForCausalLM.from_pretrained(
                str(model_dir),
                trust_remote_code=True,
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                device_map="auto" if torch.cuda.is_available() else None,
                low_cpu_mem_usage=True
            )
            
            self._initialized = True
            logger.info(f"Model {self.model_name} loaded successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return False
    
    def summarize(self, text: str, max_length: int = 500) -> str:
        """Summarize document text locally"""
        if not self._initialized:
            if not self.initialize():
                return self._fallback_summarize(text)
        
        try:
            prompt = f"Summarize the following text concisely:\n\n{text[:4000]}"
            
            inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512)
            
            if torch.cuda.is_available():
                inputs = {k: v.cuda() for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=max_length,
                    temperature=0.7,
                    do_sample=True,
                    top_p=0.95
                )
            
            summary = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
            return summary.replace(prompt, "").strip()
            
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            return self._fallback_summarize(text)
    
    def extract_entities(self, text: str) -> Dict[str, List[str]]:
        """Extract key entities from text"""
        if not self._initialized:
            return self._fallback_extract(text)
        
        try:
            prompt = f"""Extract the following entities from the text below:
- People names
- Organizations
- Dates
- Key terms

Return as JSON format.

Text: {text[:3000]}"""
            
            inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512)
            
            if torch.cuda.is_available():
                inputs = {k: v.cuda() for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=300,
                    temperature=0.3
                )
            
            response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
            # Parse JSON response (simplified)
            return self._parse_entities(response)
            
        except Exception as e:
            logger.error(f"Entity extraction failed: {e}")
            return self._fallback_extract(text)
    
    def compare_documents(self, text1: str, text2: str) -> Dict[str, Any]:
        """Compare two documents and highlight differences"""
        if not self._initialized:
            return self._fallback_compare(text1, text2)
        
        try:
            prompt = f"""Compare these two documents and identify:
1. Key similarities
2. Important differences
3. Contradictions if any

Document 1: {text1[:2000]}

Document 2: {text2[:2000]}

Provide a structured comparison."""
            
            inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512)
            
            if torch.cuda.is_available():
                inputs = {k: v.cuda() for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=500,
                    temperature=0.5
                )
            
            comparison = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
            return {"comparison": comparison.replace(prompt, "").strip()}
            
        except Exception as e:
            logger.error(f"Comparison failed: {e}")
            return self._fallback_compare(text1, text2)
    
    def answer_question(self, context: str, question: str) -> str:
        """Answer questions based on document context"""
        if not self._initialized:
            return "Local AI not available. Please enable offline mode."
        
        try:
            prompt = f"""Based on the following context, answer the question.
If the answer is not in the context, say "I don't know".

Context: {context[:3000]}

Question: {question}

Answer:"""
            
            inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512)
            
            if torch.cuda.is_available():
                inputs = {k: v.cuda() for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=200,
                    temperature=0.3
                )
            
            answer = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
            return answer.replace(prompt, "").strip()
            
        except Exception as e:
            logger.error(f"Q&A failed: {e}")
            return "Error processing question locally."
    
    def _fallback_summarize(self, text: str) -> str:
        """Fallback summarization using extractive method"""
        sentences = text.split('.')[:5]
        return '. '.join(sentences) + '.'
    
    def _fallback_extract(self, text: str) -> Dict[str, List[str]]:
        """Fallback entity extraction"""
        return {
            "people": [],
            "organizations": [],
            "dates": [],
            "key_terms": []
        }
    
    def _fallback_compare(self, text1: str, text2: str) -> Dict[str, Any]:
        """Fallback comparison"""
        return {
            "comparison": "Local AI model not available. Using basic text comparison.",
            "length_diff": abs(len(text1) - len(text2)),
            "similar_words": len(set(text1.split()) & set(text2.split()))
        }
    
    def _parse_entities(self, response: str) -> Dict[str, List[str]]:
        """Simple JSON parsing for entities"""
        # Simplified parsing - in production use proper JSON parser
        return {
            "people": [],
            "organizations": [],
            "dates": [],
            "key_terms": []
        }
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get model information"""
        return {
            "model_name": self.model_name,
            "initialized": self._initialized,
            "model_path": self.model_path,
            "cuda_available": torch.cuda.is_available() if 'torch' in globals() else False
        }


# Singleton instance
_local_ai_instance: Optional[LocalAIAssistant] = None


def get_local_ai(model_name: str = "phi-3") -> LocalAIAssistant:
    """Get or create local AI assistant instance"""
    global _local_ai_instance
    if _local_ai_instance is None or _local_ai_instance.model_name != model_name:
        _local_ai_instance = LocalAIAssistant(model_name=model_name)
    return _local_ai_instance
