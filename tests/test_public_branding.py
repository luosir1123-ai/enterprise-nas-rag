from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".md", ".py", ".sh", ".plist", ".json", ".tsx", ".html", ".svg"}


class PublicBrandingTests(unittest.TestCase):
    def test_public_project_files_do_not_expose_local_username(self) -> None:
        findings = []
        local_home = "/" + "Users" + "/letouch"
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            if local_home in path.read_text(encoding="utf-8", errors="ignore"):
                findings.append(str(path.relative_to(ROOT)))
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
