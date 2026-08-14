from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".md", ".py", ".sh", ".plist", ".json", ".yaml", ".tsx", ".html", ".svg"}
PRIVATE_IP = re.compile(r"\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b")
EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
DEPLOYMENT_ID = re.compile(r"\b[0-9a-f]{32}\b")


class PublicBrandingTests(unittest.TestCase):
    def tracked_text_files(self) -> list[Path]:
        output = subprocess.check_output(
            ["git", "ls-files", "-z"], cwd=ROOT
        ).decode("utf-8")
        return [
            ROOT / relative_path
            for relative_path in output.split("\0")
            if relative_path and Path(relative_path).suffix.lower() in TEXT_SUFFIXES
        ]

    def test_tracked_public_text_uses_only_documentation_coordinates(self) -> None:
        findings = []
        for path in self.tracked_text_files():
            if path.resolve() == Path(__file__).resolve():
                continue
            content = path.read_text(encoding="utf-8", errors="ignore")
            relative_path = path.relative_to(ROOT)
            if PRIVATE_IP.search(content):
                findings.append(f"private-ip:{relative_path}")
            for email in EMAIL.findall(content):
                if not email.casefold().endswith("@example.com"):
                    findings.append(f"email:{relative_path}")
            for home_path in re.findall(r"/Users/[^/\s]+", content):
                if home_path not in {"/Users/Shared", "/Users/your-account"}:
                    findings.append(f"home-path:{relative_path}")
            if relative_path.parts[0] == "docs" and DEPLOYMENT_ID.search(content):
                findings.append(f"deployment-id:{relative_path}")
        self.assertEqual([], findings)

    def test_portal_project_identity_uses_waimao(self) -> None:
        files = (
            ROOT / "apps/internal-portal/README.md",
            ROOT / "apps/internal-portal/package.json",
            ROOT / "apps/internal-portal/index.html",
            ROOT / "apps/internal-portal/backend/app/__init__.py",
        )
        for path in files:
            content = path.read_text(encoding="utf-8").casefold()
            self.assertNotIn("letouch internal", content, path)
            self.assertNotIn("letouch-knowledge-portal", content, path)

        public_assets = {path.name for path in (ROOT / "apps/internal-portal/public").iterdir()}
        self.assertNotIn("letouch-logo.svg", public_assets)
        self.assertNotIn("letouch-app-logo.svg", public_assets)


if __name__ == "__main__":
    unittest.main()
