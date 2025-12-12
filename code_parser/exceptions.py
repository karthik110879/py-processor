"""Custom exception classes for code parsing."""


class ParseError(Exception):
    """Raised when parsing fails."""
    
    def __init__(self, message: str, file_path: str = None, language: str = None):
        """
        Initialize ParseError.
        
        Args:
            message: Error message
            file_path: Path to file that failed to parse
            language: Programming language of the file
        """
        super().__init__(message)
        self.file_path = file_path
        self.language = language
        self.message = message
    
    def __str__(self) -> str:
        """Return string representation."""
        parts = [self.message]
        if self.file_path:
            parts.append(f"File: {self.file_path}")
        if self.language:
            parts.append(f"Language: {self.language}")
        return " | ".join(parts)


class ImportResolutionError(Exception):
    """Raised when import resolution fails."""
    
    def __init__(self, message: str, import_stmt: str = None, current_file: str = None):
        """
        Initialize ImportResolutionError.
        
        Args:
            message: Error message
            import_stmt: Import statement that failed to resolve
            current_file: File containing the import
        """
        super().__init__(message)
        self.import_stmt = import_stmt
        self.current_file = current_file
        self.message = message
    
    def __str__(self) -> str:
        """Return string representation."""
        parts = [self.message]
        if self.import_stmt:
            parts.append(f"Import: {self.import_stmt}")
        if self.current_file:
            parts.append(f"File: {self.current_file}")
        return " | ".join(parts)


class ValidationError(Exception):
    """Raised when validation fails."""
    
    def __init__(self, message: str, errors: list = None):
        """
        Initialize ValidationError.
        
        Args:
            message: Error message
            errors: List of validation errors
        """
        super().__init__(message)
        self.message = message
        self.errors = errors or []
    
    def __str__(self) -> str:
        """Return string representation."""
        if self.errors:
            return f"{self.message}: {'; '.join(str(e) for e in self.errors)}"
        return self.message

