"""Regression guards for the reviewed October security upgrade baseline."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLUSTER = ROOT / "clusters" / "belacca-production"


class SecurityUpgradeTests(unittest.TestCase):
    def text(self, path):
        return (CLUSTER / path).read_text()

    def test_critical_helm_releases_use_security_fixed_versions(self):
        for path, version in {
            "edge/helmrelease.yaml": "42.1.2",
            "policy-system/helmrelease.yaml": "3.9.2",
            "cert-manager/helmrelease.yaml": "v1.21.2",
            "headlamp/helmrelease.yaml": "0.46.0",
            "headlamp/oauth2-proxy-helmrelease.yaml": "10.7.1",
            "analytics/oauth2-proxy-helmrelease.yaml": "10.7.1",
            "dex/helmrelease.yaml": "0.26.0",
        }.items():
            with self.subTest(path=path):
                self.assertRegex(self.text(path), r'version: ["\']?' + re.escape(version) + r'["\']?\s*\n')

    def test_longhorn_upgrade_waits_for_verified_volume_recovery(self):
        self.assertIn('version: 1.12.0', self.text('longhorn/helmrelease.yaml'))
        runbook = (ROOT / 'docs/SECURITY-UPGRADES-2026-10-21.md').read_text()
        self.assertIn('Longhorn 1.12.1 remains deferred', runbook)

    def test_flux_bootstrap_field_ownership_is_migrated(self):
        text = self.text('flux-system/kustomization.yaml')
        self.assertIn('value: --override-manager=flux', text)
        self.assertIn('op: remove', text)
        self.assertIn('/resources/limits/cpu', text)
        self.assertNotIn('value: null', text)

    def test_kyverno_upgrade_keeps_crds_and_admission_available(self):
        text = self.text("policy-system/helmrelease.yaml")
        self.assertEqual(text.count("crds: CreateReplace"), 2)
        self.assertIn("crds:\n      install: true", text)
        self.assertIn("admissionController:\n      replicas: 2", text)
        self.assertNotIn("failurePolicy: Ignore", text)

    def test_flux_refresh_contains_the_scoped_webhook_policy(self):
        text = self.text("flux-system/gotk-components.yaml")
        self.assertIn("Flux Version: v2.9.6", text)
        documents = text.split("\n---\n")
        webhook = next(d for d in documents if "kind: NetworkPolicy" in d and "name: allow-webhooks\n" in d)
        self.assertIn("port: 9292", webhook)
        self.assertNotIn("port: 9090", webhook)
        self.assertIn("app: notification-controller", webhook)
        for controller, version in {
            "source-controller": "v1.9.6",
            "kustomize-controller": "v1.9.6",
            "helm-controller": "v1.6.5",
            "notification-controller": "v1.9.4",
        }.items():
            self.assertIn(f"ghcr.io/fluxcd/{controller}:{version}", text)

    def test_backup_jobs_share_one_security_fixed_immutable_python(self):
        pin = "python:3.13.16-slim-bookworm@sha256:73aa5faee130c60da030e105ec971ccf57473fbd22ce73bd6fc9ba99a40b838d"
        sources = self.text("backup/source-jobs.yaml")
        verifiers = self.text("backup/restore-verifier.yaml")
        self.assertEqual(sources.count(pin), 3)
        self.assertEqual(verifiers.count(pin), 4)
        self.assertNotIn("python:3.13.11", sources + verifiers)
        self.assertEqual(sources.count("readOnly: true"), 9)

    def test_auth_images_are_pinned_without_adding_auth_exemptions(self):
        for path in ["headlamp/oauth2-proxy-helmrelease.yaml", "analytics/oauth2-proxy-helmrelease.yaml"]:
            text = self.text(path)
            self.assertIn("newTag: v7.15.5", text)
            self.assertIn("digest: sha256:8498b0d0ef0a7b29686414000a08aee467f02d0299c9ed1e006a8f33fc017916", text)
            self.assertIn("trusted-proxy-ip: 10.42.0.0/16", text)
            self.assertNotRegex(text, r"(?m)^\s+(?:trusted-ip|skip-auth-route|skip-auth-regex):")
        headlamp = self.text("headlamp/helmrelease.yaml")
        self.assertIn("clusterRoleName: headlamp-read-only", headlamp)
        self.assertIn('"-proxy-auth=true"', headlamp)
        self.assertIn("digest: sha256:8a0ef97527544baa2b35825940ddf4db6e2d09c30cd5aa31fd269ff604cc8b75", headlamp)

    def test_cert_manager_updates_all_five_image_pins(self):
        text = self.text("cert-manager/helmrelease.yaml")
        self.assertEqual(text.count("tag: v1.21.2"), 5)
        self.assertEqual(len(re.findall(r"digest: sha256:[0-9a-f]{64}", text)), 5)
        self.assertNotIn("v1.21.1", text)

    def test_prometheus_runtime_and_validation_tool_versions_stay_aligned(self):
        deployment = self.text("observability/deployment.yaml")
        workflow = (ROOT / ".github/workflows/validate.yml").read_text()
        self.assertIn("prom/prometheus:v3.13.5@sha256:aafa9d694e6a883c02db516d9f6e5b84e14195f49a2a6456a4cca815edda72b9", deployment)
        self.assertIn("version='3.13.5'", workflow)
        self.assertIn("0388822ace519c5a3a8ef556a541ce1b536e21d872f82deded465bd27a5a0699", workflow)
        self.assertIn("type: Recreate", deployment)
        self.assertIn("claimName: prometheus-native-data", deployment)

    def test_redis_is_patched_without_changing_its_storage_contract(self):
        text = self.text("mutandae/redis.yaml")
        self.assertIn("redis:7.4.11-alpine@sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499", text)
        self.assertIn("storageClassName: longhorn", text)
        self.assertIn("name: mutandae-redis-auth", text)
        self.assertIn("storage: 5Gi", text)

    def test_vault_major_upgrade_is_not_silently_bundled(self):
        text = self.text("mutandae/vault.yaml")
        self.assertEqual(text.count("hashicorp/vault:1.21.4@sha256:"), 2)
        self.assertIn("whenDeleted: Retain", text)
        self.assertNotIn("hashicorp/vault:2.", text)

    def test_flux_web_chart_is_immutable(self):
        text = self.text("flux-web/oci-repository.yaml")
        self.assertIn("chart 0.61.0", text)
        self.assertIn("digest: sha256:8c039527c4a20599bc49bf69fa944e4ae08a0d7c1d585664261d9e78e51b0bde", text)
        self.assertNotIn("semver:", text)


if __name__ == "__main__":
    unittest.main()
