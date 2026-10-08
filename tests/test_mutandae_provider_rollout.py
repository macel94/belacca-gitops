from pathlib import Path
import unittest
import ipaddress
import yaml

ROOT = Path(__file__).resolve().parents[1]


class MutandaeProviderRolloutTests(unittest.TestCase):
    def test_live_configuration_revision_does_not_target_preview(self):
        documents = list(yaml.safe_load_all((ROOT / 'clusters/belacca-production/native-applications.yaml').read_text()))
        app = next(d for d in documents if d['metadata']['name'] == 'mutandae')
        patches = app['spec']['patches']
        self.assertEqual(len(patches), 1)
        self.assertEqual(patches[0]['target'], {'kind': 'Deployment', 'name': 'mutandae'})
        patch = yaml.safe_load(patches[0]['patch'])
        self.assertEqual(patch['metadata']['name'], 'mutandae')
        self.assertEqual(set(patch['spec']), {'template'})
        self.assertEqual(set(patch['spec']['template']), {'metadata'})
        revision = patch['spec']['template']['metadata']['annotations']['mutandae.com/provider-config-revision']
        self.assertEqual(revision, '2026-10-08-bare-sender')

    def test_live_sender_is_a_bare_mailbox(self):
        config = yaml.safe_load((ROOT / 'clusters/belacca-production/mutandae/sales-config.yaml').read_text())['data']
        self.assertEqual(config['MUTANDAE_EMAIL_FROM'], 'forms@notify.mutandae.com')
        self.assertEqual(config['MUTANDAE_AI_TENANTS'], 'mutandae-sales')
        self.assertEqual(config['MUTANDAE_EMAIL_TENANTS'], 'mutandae-sales')

    def test_provider_egress_is_live_only_public_ipv4_on_https(self):
        policy = yaml.safe_load((ROOT / 'clusters/belacca-production/mutandae/network-policy-providers.yaml').read_text())['spec']
        self.assertEqual(policy['podSelector'], {'matchLabels': {'app.kubernetes.io/name': 'mutandae'}})
        self.assertEqual(policy['policyTypes'], ['Egress'])
        self.assertNotIn('ingress', policy)
        self.assertEqual(len(policy['egress']), 1)
        rule = policy['egress'][0]
        self.assertEqual(rule['ports'], [{'protocol': 'TCP', 'port': 443}])
        self.assertEqual(len(rule['to']), 4)
        for destination in rule['to']:
            self.assertEqual(set(destination), {'ipBlock'})
            network = ipaddress.ip_network(destination['ipBlock']['cidr'])
            self.assertEqual(network.version, 4)
            self.assertEqual(network.prefixlen, 32)
            self.assertTrue(network.network_address.is_global)
