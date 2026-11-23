import re
import unittest
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


class ProjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.collector = yaml.safe_load((ROOT / 'collector.yaml').read_text())
        cls.compose = yaml.safe_load((ROOT / 'docker-compose.yaml').read_text())
        cls.export = yaml.safe_load((ROOT / 'zabbix/zabbix_npm_apm_template.yaml').read_text())

    def test_collector_pipeline_references(self):
        cfg = self.collector
        for pipeline in cfg['service']['pipelines'].values():
            for key, group in [('receivers', 'receivers'), ('exporters', 'exporters'), ('processors', 'processors')]:
                for comp in pipeline.get(key, []):
                    self.assertIn(comp, cfg.get(group, {}) if comp != 'count' else cfg['connectors'])
        self.assertIn('count', cfg['connectors'])

    def test_docker_compose_only_collector(self):
        self.assertEqual(list(self.compose['services']), ['otel-collector'])
        service = self.compose['services']['otel-collector']
        self.assertTrue(all(str(v).endswith(':ro') for v in service['volumes']))
        self.assertEqual(set(service['environment']), {'ZABBIX_OTLP_ENDPOINT', 'OTEL_HOST_NAME', 'OTEL_ENVIRONMENT'})

    def test_resource_env_variables(self):
        for receiver in self.collector['receivers'].values():
            resource = receiver['resource']
            self.assertEqual(resource['service.name'], 'nginx-proxy-manager')
            self.assertEqual(resource['host.name'], '${env:OTEL_HOST_NAME}')
            self.assertEqual(resource['deployment.environment.name'], '${env:OTEL_ENVIRONMENT}')

    def test_template_discovery_and_uuid_uniqueness(self):
        t = self.export['zabbix_export']['templates'][0]
        self.assertEqual(self.export['zabbix_export']['version'], '8.0')
        self.assertEqual(len(t['discovery_rules']), 2)
        self.assertEqual({d['type'] for d in t['discovery_rules']}, {'SCRIPT'})
        self.assertIn('{#ZBX.HOST}', t['discovery_rules'][0]['params'])
        u = [t['uuid']]
        for d in t['discovery_rules']:
            u.append(d['uuid'])
            for i in d['item_prototypes']:
                u.append(i['uuid'])
                u += [tr['uuid'] for tr in i.get('trigger_prototypes', [])]
        u += [w['uuid'] for w in t.get('dashboards', [])]
        self.assertEqual(len(u), len(set(u)))

    def test_template_no_deployment_specific_values(self):
        content=(ROOT / 'zabbix/zabbix_npm_apm_template.yaml').read_text()
        self.assertNotIn('zabbix_apm.otel_metrics_sum', content)
        self.assertIn('{$NPM.CH.DATABASE}', content)
        self.assertIn('{$NPM.CH.PASSWORD}', content)
        template=self.export['zabbix_export']['templates'][0]
        self.assertFalse(any(m['macro']=='{$NPM.CH.PASSWORD}' for m in template.get('macros', [])))

    def test_standard_npm_log_format(self):
        expression=self.collector['receivers']['file_log/npm_access']['operators'][0]['regex']
        for status in ('200','301','404','502'):
            log=f'[24/Nov/2026:10:15:00 +0000] - 200 {status} - GET https example.org "/path" [Client 192.0.2.10]'
            match=re.search(expression, log)
            self.assertIsNotNone(match)
            self.assertEqual(match['http_status'], status)
            self.assertEqual(match['http_host'], 'example.org')
        self.assertIsNone(re.search(expression, 'not an NPM access log'))


if __name__ == '__main__':
    unittest.main()
