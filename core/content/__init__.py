"""
Content Registry for RHCSA Simulator v4.0.0
Loads domain-based learning content modules aligned with EX200 v10 exam objectives.
"""

import importlib
import logging

from config.exam_objectives import get_objectives


logger = logging.getLogger(__name__)


# Domain module mapping
_DOMAIN_MODULES = {
    1: "core.content.domain_1_software",
    2: "core.content.domain_2_boot",
    3: "core.content.domain_3_users",
    4: "core.content.domain_4_storage",
    5: "core.content.domain_5_networking",
    6: "core.content.domain_6_services",
    7: "core.content.domain_7_security",
    8: "core.content.domain_8_automation",
    9: "core.content.domain_9_containers",
}


class ContentRegistry:
    """Central registry for all learning content, organized by exam domain."""

    _content = {}
    _initialized = False

    @classmethod
    def _enrich_topic(cls, category, topic, domain_num):
        """
        Add common study metadata without replacing topic-specific content.

        Existing domain files remain focused on educational material. This
        method adds the metadata needed by Learn, Practice and Study Tracker.
        """
        if not isinstance(topic, dict):
            return topic

        objectives = get_objectives().get(domain_num, {})

        enriched = dict(topic)
        enriched.setdefault("study_id", category)
        enriched.setdefault("domain", domain_num)
        enriched.setdefault(
            "domain_name",
            objectives.get("name", ""),
        )
        enriched.setdefault(
            "official_objectives",
            list(objectives.get("objectives", [])),
        )
        enriched.setdefault(
            "content_sources",
            [
                "official_rhcsa",
                "sander_van_vugt",
            ],
        )
        enriched.setdefault("sander_chapter", None)

        return enriched

    @classmethod
    def initialize(cls):
        """Load all domain content modules."""
        if cls._initialized:
            return

        for domain_num, module_path in _DOMAIN_MODULES.items():
            try:
                mod = importlib.import_module(module_path)
                content = getattr(mod, "CONTENT", {})

                for category, topic in content.items():
                    cls._content[category] = cls._enrich_topic(
                        category,
                        topic,
                        domain_num,
                    )

                logger.debug(
                    f"Loaded domain {domain_num}: "
                    f"{len(content)} categories"
                )
            except ImportError as exc:
                logger.warning(
                    f"Could not load {module_path}: {exc}"
                )
            except Exception as exc:
                logger.error(
                    f"Error loading {module_path}: {exc}"
                )

        cls._initialized = True
        logger.info(
            f"ContentRegistry initialized: "
            f"{len(cls._content)} categories"
        )

    @classmethod
    def get_topic(cls, category):
        """Get learning content for a category."""
        cls.initialize()
        return cls._content.get(category)

    @classmethod
    def get_all_categories(cls):
        """Get all available category keys."""
        cls.initialize()
        return list(cls._content.keys())

    @classmethod
    def get_categories_for_domain(cls, domain_number):
        """Get category keys belonging to a specific domain."""
        cls.initialize()

        objectives = get_objectives()
        domain = objectives.get(domain_number, {})

        return [
            category
            for category in domain.get("categories", [])
            if category in cls._content
        ]

    @classmethod
    def get_domain_content(cls, domain_number):
        """Get all content dicts for a domain, keyed by category."""
        cls.initialize()

        categories = cls.get_categories_for_domain(domain_number)

        return {
            category: cls._content[category]
            for category in categories
        }

    @classmethod
    def get_study_metadata(cls, category):
        """
        Return only the common study metadata for a category.
        """
        topic = cls.get_topic(category)

        if not topic:
            return None

        return {
            "study_id": topic.get("study_id"),
            "domain": topic.get("domain"),
            "domain_name": topic.get("domain_name"),
            "official_objectives": list(
                topic.get("official_objectives", [])
            ),
            "content_sources": list(
                topic.get("content_sources", [])
            ),
            "sander_chapter": topic.get("sander_chapter"),
        }
