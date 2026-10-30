import tempfile
import unittest
from pathlib import Path

from knowledge_base import MarkdownKnowledgeBase


class KnowledgeBaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = MarkdownKnowledgeBase(Path(__file__).resolve().parents[2] / "sociapi_agent_knowledge_base")
        cls.base.reload()

    def test_requested_questions_retrieve_supported_source_files(self):
        cases = [
            ("Who is the Founder of Sociapi Society?", "02_sociapi_society.md", "Muhammad Zuhair Zeb"),
            ("What is Sociapi Society's tagline?", "02_sociapi_society.md", "From Ideas to Intelligence"),
            ("What are the Sociapi brand colors?", "04_brand_and_communication_rules.md", "#517642"),
            ("What is my main career direction?", "01_user_profile_and_cv.md", "WordPress"),
            ("What is the current RepoGuard project title?", "06_fyp_repoguard.md", "English and Roman Urdu"),
            ("What is the difference between confirmed facts and historical information?", "08_fact_register_and_uncertainty.md", "Historical"),
        ]
        for query, source, evidence in cases:
            with self.subTest(query=query):
                results = self.base.retrieve(query, limit=4)
                matches = [item for item in results if item["source"].endswith(source)]
                self.assertTrue(matches, f"No retrieved excerpt from {source}: {results}")
                self.assertTrue(any(evidence.casefold() in item["text"].casefold() for item in matches))

    def test_general_sociapi_questions_prioritize_society_source_only(self):
        for query in ("What is Sociapi?", "What is Sociapi Society?", "Tell me about Sociapi"):
            with self.subTest(query=query):
                results = self.base.retrieve(query, limit=4)
                self.assertTrue(results)
                self.assertTrue(all(item["source"].endswith("02_sociapi_society.md") for item in results), results)
                text = "\n".join(item["text"] for item in results).casefold()
                for evidence in ("volunteer-based", "from ideas to intelligence", "artificial intelligence", "workshops", "classroom learning"):
                    self.assertIn(evidence, text)
                self.assertNotIn("mentorship", text)
                self.assertNotIn("open source", text)
                self.assertTrue(all(item["heading"] in {"Identity", "Mission and positioning"} for item in results))

    def test_brand_source_is_used_only_for_brand_related_sociapi_questions(self):
        general = self.base.retrieve("What is Sociapi?", limit=4)
        brand = self.base.retrieve("What are Sociapi's brand colors?", limit=4)
        self.assertFalse(any(item["source"].endswith("04_brand_and_communication_rules.md") for item in general))
        self.assertTrue(brand)
        self.assertTrue(all(item["source"].endswith("04_brand_and_communication_rules.md") for item in brand))
        self.assertTrue(any("#517642" in item["text"] for item in brand))

    def test_general_sociapi_chat_prompt_restricts_sources_and_unsupported_claims(self):
        from router import AGENTS
        from web_app import _messages
        prompt_messages = _messages(AGENTS["general"], "What is Sociapi?", [], {}, False)
        context = "\n".join(str(message.content) for message in prompt_messages)
        self.assertIn("Source: sociapi_agent_knowledge_base\\02_sociapi_society.md", context)
        excerpts = context.partition("Relevant excerpts")[2]
        self.assertNotIn("04_brand_and_communication_rules.md", excerpts)
        self.assertIn("Do not characterize Sociapi primarily as a WordPress organization", context)
        self.assertNotIn("open source", excerpts.casefold())
        self.assertNotIn("mentorship", excerpts.casefold())

    def test_email_retrieval_uses_request_specific_sources(self):
        event_email = self.base.retrieve("Draft an email about Sociapi Boot Camp 2026 certificate distribution", limit=3)
        recruitment_email = self.base.retrieve("Draft an email to shortlisted Sociapi Society applicants", limit=3)
        self.assertTrue(any(item["source"].endswith("03_events_projects_operations.md") and item["heading"] == "Sociapi Boot Camp 2026" for item in event_email))
        self.assertTrue(any(item["source"].endswith("02_sociapi_society.md") and item["heading"] == "Recruitment" for item in recruitment_email))
        self.assertFalse(any(item["source"].endswith("01_user_profile_and_cv.md") for item in event_email + recruitment_email))

    def test_chainlit_email_prompt_uses_the_same_evidence_rules_without_internal_citations(self):
        from app import _make_messages
        from router import AGENTS
        request = "Write an email about Sociapi Boot Camp 2026 certificates."
        prompt_messages = _make_messages(AGENTS["writing"], request, [], {"language": "English"})
        prompt = "\n".join(str(message.content) for message in prompt_messages)
        self.assertIn("Never promise a future email, meeting, offer letter, or onboarding step", prompt)
        self.assertIn("Source: sociapi_agent_knowledge_base\\03_events_projects_operations.md", prompt)
        self.assertIn("Keep local file paths out of the draft", prompt)

    def test_email_prompt_requires_supported_facts_and_safe_omissions(self):
        from prompt_rules import EMAIL_WRITING_GUIDANCE, is_email_writing_request
        from router import AGENTS
        from web_app import _messages
        request = "Draft a professional email to shortlisted Sociapi Society applicants about joining."
        self.assertTrue(is_email_writing_request(request, "writing"))
        self.assertFalse(is_email_writing_request("Write a short event announcement", "writing"))
        prompt_messages = _messages(AGENTS["writing"], request, [], {}, False)
        prompt = "\n".join(str(message.content) for message in prompt_messages)
        for required_rule in ("only when explicitly supplied", "assumptions", "Keep local file paths out of the draft", "Never promise a future email", "reporting structure", "do not promise to provide them later", "professional, concise, natural"):
            with self.subTest(rule=required_rule):
                self.assertIn(required_rule, prompt)
        self.assertIn("Source: sociapi_agent_knowledge_base\\02_sociapi_society.md", prompt)
        self.assertNotIn("04_brand_and_communication_rules.md", prompt.partition("Relevant excerpts")[2])
        self.assertIn("responsibilities, reporting structure, or joining date", EMAIL_WRITING_GUIDANCE)

    def test_founder_and_role_questions_retrieve_founder_facts_without_legal_noise(self):
        cases = (
            "Who owns Sociapi?",
            "Who founded Sociapi?",
            "Who came up with the idea of Sociapi?",
            "Who is the Co-Founder?",
            "Who is the Teacher Advisor?",
        )
        for query in cases:
            with self.subTest(query=query):
                results = self.base.retrieve(query, limit=4)
                text = "\n".join(item["text"] for item in results).casefold()
                headings = {item["heading"] for item in results}
                self.assertIn("muhammad zuhair zeb", text)
                self.assertIn("muhammad mudassir", text)
                self.assertIn("dr. naveed abbas", text)
                self.assertTrue(headings & {"Identity", "Leadership and roles"})
                self.assertFalse(any(item["heading"] == "Registration status" for item in results))
                self.assertFalse(any(item["source"].endswith("08_fact_register_and_uncertainty.md") for item in results))

    def test_legal_registration_query_retrieves_registration_fact_only_when_asked(self):
        results = self.base.retrieve("Is Sociapi legally registered?", limit=4)
        self.assertTrue(any(item["heading"] == "Registration status" for item in results))
        registration = next(item["text"] for item in results if item["heading"] == "Registration status")
        self.assertIn("not formally registered", registration)
        self.assertFalse(any(item["source"].endswith("08_fact_register_and_uncertainty.md") for item in results))

    def test_explicit_reference_request_can_retrieve_public_society_links(self):
        results = self.base.retrieve("Who founded Sociapi? Please provide references", limit=4)
        links = [item["text"] for item in results if item["heading"] == "Official links and contact"]
        self.assertTrue(links)
        self.assertIn("https://sociapis.vercel.app", "\n".join(links))

    def test_governance_prompt_answers_naturally_and_hides_retrieval_details(self):
        from prompt_rules import SOCIAPI_GOVERNANCE_GUIDANCE
        from router import AGENTS
        from web_app import _messages
        questions = (
            "Who owns Sociapi?",
            "Who founded Sociapi?",
            "Who came up with the idea of Sociapi?",
            "Who is the Co-Founder?",
            "Who is the Teacher Advisor?",
            "Is Sociapi legally registered?",
        )
        for question in questions:
            with self.subTest(question=question):
                messages = _messages(AGENTS["general"], question, [], {}, False)
                prompt = "\n".join(str(message.content) for message in messages)
                for concept in ("Muhammad Zuhair Zeb", "original creator", "Muhammad Mudassir", "Dr. Naveed Abbas", "adapt the wording", "Do not add a caveat or sentence about legal or corporate ownership", "Do not describe the Society as member-owned", "cite its Markdown filename briefly", "cite public web facts with clickable source links"):
                    self.assertIn(concept.casefold(), prompt.casefold())
                self.assertIn("02_sociapi_society.md | Section: Leadership and roles", prompt)
                self.assertNotIn("unavailable in the available records", prompt)
                if question == "Is Sociapi legally registered?":
                    self.assertIn("Registration status", prompt)
                    self.assertIn("Its current status should be checked", prompt)
        self.assertIn("Do not describe the Society as member-owned", SOCIAPI_GOVERNANCE_GUIDANCE)

    def test_chainlit_governance_prompt_hides_internal_source_attribution(self):
        from app import _make_messages
        from router import AGENTS
        messages = _make_messages(AGENTS["general"], "Who owns Sociapi?", [], {"language": "English"})
        prompt = "\n".join(str(message.content) for message in messages)
        self.assertIn("02_sociapi_society.md | Section: Leadership and roles", prompt)
        self.assertIn("Muhammad Zuhair Zeb is the Founder and original creator", prompt)
        self.assertIn("cite its Markdown filename briefly", prompt)
        self.assertNotIn("Never expose Markdown filenames", prompt)

    def test_governance_follow_up_resolves_sociapi_from_recent_user_history(self):
        from router import AGENTS
        from web_app import _messages
        messages = _messages(AGENTS["general"], "Who manages it?", [("user", "I am asking about Sociapi Society.")], {}, False)
        prompt = "\n".join(str(message.content) for message in messages)
        self.assertIn("02_sociapi_society.md | Section: Leadership and roles", prompt)
        self.assertNotIn("08_fact_register_and_uncertainty.md", prompt)

    def test_unrelated_prompt_does_not_receive_sociapi_governance_facts(self):
        from router import AGENTS
        from web_app import _messages
        messages = _messages(AGENTS["general"], "How do I boil pasta?", [], {}, False)
        prompt = "\n".join(str(message.content) for message in messages)
        self.assertNotIn("Muhammad Zuhair Zeb", prompt)
        self.assertNotIn("original creator", prompt)

    def test_unrelated_question_returns_no_knowledge_context(self):
        self.assertEqual(self.base.retrieve("How do I bake sourdough bread?"), [])

    def test_retrieved_source_is_added_to_web_chat_prompt(self):
        from router import AGENTS
        from web_app import _messages
        prompt_messages = _messages(AGENTS["general"], "What are Sociapi Society's brand colors?", [], {}, False)
        context = "\n".join(str(message.content) for message in prompt_messages)
        self.assertIn("04_brand_and_communication_rules.md", context)
        self.assertIn("#517642", context)

    def test_results_include_filename_heading_and_debug_score(self):
        result = self.base.retrieve("RepoGuard project title", limit=1)[0]
        self.assertIn("source", result)
        self.assertIn("heading", result)
        self.assertGreater(result["score"], 0)

    def test_changed_markdown_is_reloaded_without_rebuilding_model(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            doc = root / "README.md"
            doc.write_text("# Team\nSociapi team uses green notebooks.", encoding="utf-8")
            kb = MarkdownKnowledgeBase(root)
            self.assertIn("green notebooks", kb.retrieve("green notebooks")[0]["text"])
            doc.write_text("# Team\nSociapi team uses blue notebooks.", encoding="utf-8")
            self.assertIn("blue notebooks", kb.retrieve("blue notebooks")[0]["text"])
            self.assertEqual(kb.retrieve("green notebooks"), [])

    def test_missing_directory_is_reported_clearly(self):
        with tempfile.TemporaryDirectory() as temp:
            missing = Path(temp) / "missing"
            kb = MarkdownKnowledgeBase(missing)
            status = kb.reload()
            self.assertEqual(status["document_count"], 0)
            self.assertTrue(any("not found" in error for error in status["errors"]))


if __name__ == "__main__":
    unittest.main()

