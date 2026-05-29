"""
Document Templates Schemas
Pydantic models for document template generation requests and responses.
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List


class TemplateGenerateRequest(BaseModel):
    """Request model for generating a document from template."""
    data: Dict[str, Any] = Field(
        ..., 
        description="Template-specific data fields to populate the document"
    )
    filename_prefix: Optional[str] = Field(
        None,
        description="Optional prefix for the generated filename"
    )


class TemplateInfo(BaseModel):
    """Information about a single template."""
    type: str = Field(..., description="Template type identifier")
    name: str = Field(..., description="Human-readable template name")
    category: Optional[str] = Field(None, description="Template category")
    formats: List[str] = Field(..., description="Supported output formats (docx, pdf)")
    description: Optional[str] = Field(None, description="Template description")


class TemplateListResponse(BaseModel):
    """Response model for listing templates."""
    templates: List[TemplateInfo] = Field(..., description="List of available templates")


class TemplateCategoryResponse(BaseModel):
    """Response model for template categories."""
    category: str = Field(..., description="Category name")
    templates: List[Dict[str, Any]] = Field(
        ..., 
        description="List of templates in this category"
    )


class TemplatePreviewResponse(BaseModel):
    """Response model for template preview information."""
    template_type: str = Field(..., description="Template type identifier")
    name: str = Field(..., description="Template name")
    description: str = Field(..., description="Template description")
    sections: List[str] = Field(..., description="Document sections included")
    required_fields: List[str] = Field(..., description="Required data fields")
    optional_fields: List[str] = Field(..., description="Optional data fields")
