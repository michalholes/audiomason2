"""Text utilities plugin - based on AM1 util.py.

Provides text processing functions:
- strip_diacritics: Remove accents from text
- slug: Create filesystem-safe slugs
- clean_text: Clean and normalize text
"""

from __future__ import annotations

import re
import unicodedata


class TextUtilsPlugin:
    """Text utilities plugin.

    This is a utility plugin that doesn't implement any interface.
    It provides helper functions used by other plugins.
    """

    @staticmethod
    def strip_diacritics(text: str) -> str:
        """Remove diacritics (accents) from text.

        Example:
            "Příliš žluťoučký kůň"
                -> "Prilis zlutoucky kun"

        Args:
            text: Input text with diacritics

        Returns:
            Text without diacritics
        """
        if not text:
            return text

        # Normalize to NFD (decomposed form)
        # This separates base characters from combining marks
        nfd = unicodedata.normalize("NFD", text)

        # Filter out combining marks (category Mn)
        stripped = "".join(char for char in nfd if unicodedata.category(char) != "Mn")

        # Normalize back to NFC (composed form)
        return unicodedata.normalize("NFC", stripped)

    @staticmethod
    def slug(text: str, separator: str = "-") -> str:
        """Create filesystem-safe slug from text.

        Example:
            "George Orwell - 1984"
                -> "george-orwell-1984"
            "Příliš žluťoučký kůň"
                -> "prilis-zlutoucky-kun"

        Args:
            text: Input text
            separator: Separator character (default: "-")

        Returns:
            Filesystem-safe slug
        """
        if not text:
            return ""

        # Strip diacritics first
        text = TextUtilsPlugin.strip_diacritics(text)

        # Convert to lowercase
        text = text.lower()

        # Replace spaces and special chars with separator
        text = re.sub(r"[^\w\s-]", "", text)
        text = re.sub(r"[-\s]+", separator, text)

        # Remove leading/trailing separators
        text = text.strip(separator)

        return text

    @staticmethod
    def clean_text(text: str) -> str:
        """Clean and normalize text.

        - Strips leading/trailing whitespace
        - Normalizes internal whitespace
        - Removes control characters

        Args:
            text: Input text

        Returns:
            Cleaned text
        """
        if not text:
            return ""

        # Remove control characters
        text = "".join(char for char in text if unicodedata.category(char)[0] != "C")

        # Normalize whitespace
        text = " ".join(text.split())

        # Strip
        text = text.strip()

        return text

    @staticmethod
    def sanitize_filename(name: str, max_length: int = 100) -> str:
        """Sanitize string for use in filename.

        Args:
            name: Original name
            max_length: Maximum length

        Returns:
            Sanitized filename
        """
        if not name:
            return "Unnamed"

        # Remove problematic characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, "_")

        # Clean
        name = TextUtilsPlugin.clean_text(name)

        # Remove leading/trailing dots and spaces
        name = name.strip(". ")

        # Limit length
        if len(name) > max_length:
            name = name[:max_length].strip()

        return name if name else "Unnamed"

    @staticmethod
    def truncate(text: str, max_length: int, suffix: str = "...") -> str:
        """Truncate text to maximum length.

        Args:
            text: Input text
            max_length: Maximum length (including suffix)
            suffix: Suffix to append if truncated

        Returns:
            Truncated text
        """
        if not text or len(text) <= max_length:
            return text

        truncate_at = max_length - len(suffix)
        return text[:truncate_at].rstrip() + suffix

    @staticmethod
    def normalize_whitespace(text: str) -> str:
        """Normalize whitespace in text.

        - Multiple spaces → single space
        - Tabs → spaces
        - Newlines preserved but cleaned

        Args:
            text: Input text

        Returns:
            Text with normalized whitespace
        """
        if not text:
            return ""

        # Replace tabs with spaces
        text = text.replace("\t", " ")

        # Normalize spaces on each line
        lines = text.split("\n")
        lines = [" ".join(line.split()) for line in lines]

        # Join back
        return "\n".join(lines)

    @staticmethod
    def title_case(text: str) -> str:
        """Convert to title case with smart handling.

        - Capitalizes first letter of each word
        - Keeps certain words lowercase (articles, conjunctions)
        - Always capitalizes first and last word

        Args:
            text: Input text

        Returns:
            Title-cased text
        """
        if not text:
            return ""

        # Words that should stay lowercase (unless first/last)
        lowercase_words = {
            "a",
            "an",
            "and",
            "as",
            "at",
            "but",
            "by",
            "for",
            "in",
            "of",
            "on",
            "or",
            "the",
            "to",
        }

        words = text.split()
        result = []

        for i, word in enumerate(words):
            # First and last words always capitalized
            if i == 0 or i == len(words) - 1:
                result.append(word.capitalize())
            # Small words stay lowercase
            elif word.lower() in lowercase_words:
                result.append(word.lower())
            # Everything else capitalized
            else:
                result.append(word.capitalize())

        return " ".join(result)
