# -*- coding: utf-8 -*-

import os
import unittest

import six
from pyramid.config import Configurator
import skosprovider
from skosprovider.providers import DictionaryProvider
from skosprovider.uri import UriPatternGenerator
from skosprovider_sqlalchemy.models import Base, ConceptScheme, LabelType, Language, MatchType
from skosprovider_sqlalchemy.providers import SQLAlchemyProvider
from skosprovider_sqlalchemy.utils import import_provider
from sqlalchemy.orm import sessionmaker
import transaction
from webtest import TestApp
from pyramid import testing
from zope.sqlalchemy import ZopeTransactionExtension
from pyramid.paster import get_appsettings
from sqlalchemy import engine_from_config

from atramhasis import includeme
from atramhasis.db import db
from atramhasis.protected_resources import ProtectedResourceException, ProtectedResourceEvent
from fixtures.data import trees, geo, larch, chestnut, species
from fixtures.materials import materials


here = os.path.dirname(__file__)
settings = get_appsettings(os.path.join(here, '../', 'tests/conf_test.ini'))

json_value = {
    "type": "concept",
    "broader": [],
    "narrower": [],
    "related": [],
    "labels": [
        {
            "type": "prefLabel",
            "language": "en",
            "label": "The Larch"
        }
    ],
    "notes": []
}

json_value_relations = {
    "broader": [{"id": 12}],
    "id": 13,
    "related": [],
    "type": "concept",
    "labels": [{
                   "label": "koperlegeringen",
                   "language": "nl",
                   "type": "prefLabel"
               }],
    "label": "koperlegeringen",
    "notes": [],
    "narrower": [{"id": 15}, {"id": 14}]
}

json_value_invalid = """{
    "type": "concept",
    "broader": [],
    "narrower": [],
    "related"[]: [],
    "labels": [
        {
            "type": "prefLabel",
            "language": "en",
            "label": "The Larch"
        }
    ],
    "notes": []}
}"""

json_collection_value = {
    "labels": [{
                   "language": "nl",
                   "label": "Test verzameling",
                   "type": "prefLabel"
               }],
    "type": "collection",
    "label": "Test verzameling",
    "members": [{"id": 333}, {"id": 7}],
    "notes": [{
                  "note": "een notitie",
                  "type": "note",
                  "language": "nl"
              }]
}

TEST = DictionaryProvider(
    {
        'id': 'TEST',
        'default_language': 'nl',
        'subject': ['biology']
    },
    [larch, chestnut, species],
    concept_scheme=skosprovider.skos.ConceptScheme('http://id.trees.org')
)


class FunctionalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = engine_from_config(settings, prefix='sqlalchemy.')
        cls.session_maker = sessionmaker(
            bind=cls.engine,
            extension=ZopeTransactionExtension()
        )

    def setUp(self):
        self.config = Configurator(settings=settings)
        self.config.add_route('login', '/auth/login')
        self.config.add_route('logout', '/auth/logout')
        includeme(self.config)
        self.config.add_static_view('atramhasis/static', 'atramhasis:static')

        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)

        Base.metadata.bind = self.engine

        self.config.registry.dbmaker = self.session_maker
        self.config.add_request_method(db, reify=True)

        with transaction.manager:
            local_session = self.session_maker()
            import_provider(trees, ConceptScheme(id=1, uri='urn:x-skosprovider:trees'), local_session)
            import_provider(materials, ConceptScheme(id=4, uri='urn:x-vioe:materials'), local_session)
            import_provider(geo, ConceptScheme(id=2), local_session)
            local_session.add(ConceptScheme(id=3))
            local_session.add(LabelType('hiddenLabel', 'A hidden label.'))
            local_session.add(LabelType('altLabel', 'An alternative label.'))
            local_session.add(LabelType('prefLabel', 'A preferred label.'))
            local_session.add(Language('nl', 'Dutch'))
            local_session.add(Language('en', 'English'))

            local_session.add(MatchType('broadMatch', ''))
            local_session.add(MatchType('closeMatch', ''))
            local_session.add(MatchType('exactMatch', ''))
            local_session.add(MatchType('narrowMatch', ''))
            local_session.add(MatchType('relatedMatch', ''))
            local_session.add(Language(id='de', name='test'))

        TREES = SQLAlchemyProvider(
            {'id': 'TREES', 'conceptscheme_id': 1},
            self.config.registry.dbmaker
        )

        GEO = SQLAlchemyProvider(
            {'id': 'GEOGRAPHY', 'conceptscheme_id': 2},
            self.config.registry.dbmaker
        )

        STYLES = SQLAlchemyProvider(
            {'id': 'STYLES', 'conceptscheme_id': 3},
            self.config.registry.dbmaker
        )

        MATERIALS = SQLAlchemyProvider(
            {'id': 'MATERIALS', 'conceptscheme_id': 4},
            self.config.registry.dbmaker,
            uri_generator=UriPatternGenerator('urn:x-vioe:materials:%s')
        )

        self.config.add_subscriber(self.mock_event_handler, ProtectedResourceEvent)

        skosregis = self.config.get_skos_registry()
        skosregis.register_provider(TREES)
        skosregis.register_provider(GEO)
        skosregis.register_provider(STYLES)
        skosregis.register_provider(MATERIALS)
        skosregis.register_provider(TEST)

        self.app = self.config.make_wsgi_app()
        self.testapp = TestApp(self.app)

    def tearDown(self):
        testing.tearDown()

    @staticmethod
    def mock_event_handler(event):
        if event.uri == 'http://localhost/conceptschemes/GEOGRAPHY/c/9':
            referenced_in = ['urn:someobject', 'http://test.test.org/object/2']
            raise ProtectedResourceException('resource {0} is still in use, preventing operation'.format(event.uri),
                                             referenced_in)


class HtmlFunctionalTests(FunctionalTests):
    def _get_default_headers(self):
        return {'Accept': 'text/html'}

    def test_get_home(self):
        res = self.testapp.get('/', headers=self._get_default_headers())
        self.assertEqual('200 OK', res.status)
        self.assertIn('text/html', res.headers['Content-Type'])


class CsvFunctionalTests(FunctionalTests):
    def test_get_csv(self):
        response = self.testapp.get('/conceptschemes/TREES/c.csv?ctype=collection&label=')
        self.assertEqual('200 OK', response.status)
        self.assertIn('text/csv', response.headers['Content-Type'])
        self.assertIn('attachment;filename="atramhasis_export.csv"', response.headers['Content-Disposition'])

    def test_unicode_csv(self):
        response = self.testapp.get('/conceptschemes/TREES/c.csv?label=Chestnut&_LOCALE_=fr')
        data = response.body.decode('utf-8')
        self.assertIsInstance(data, six.text_type)
        self.assertEqual('200 OK', response.status)
        self.assertIn('text/csv', response.headers['Content-Type'])
        self.assertIn('attachment;filename="atramhasis_export.csv"', response.headers['Content-Disposition'])
        self.assertIn(u'la châtaigne', data)

    def test_get_csv_all(self):
        response = self.testapp.get('/conceptschemes/TREES/c.csv')
        self.assertEqual('200 OK', response.status)
        self.assertIn('text/csv', response.headers['Content-Type'])
        self.assertIn('attachment;filename="atramhasis_export.csv"', response.headers['Content-Disposition'])


class RestFunctionalTests(FunctionalTests):
    def _get_default_headers(self):
        return {'Accept': 'application/json'}

    def test_get_concept(self):
        res = self.testapp.get('/conceptschemes/TREES/c/1', headers=self._get_default_headers())
        self.assertEqual('200 OK', res.status)
        self.assertIn('application/json', res.headers['Content-Type'])
        self.assertIsNotNone(res.json['id'])
        self.assertEqual(res.json['id'], 1)
        self.assertEqual(res.json['type'], 'concept')

    def test_get_concept_dictprovider(self):
        res = self.testapp.get('/conceptschemes/TEST/c/1', headers=self._get_default_headers())
        self.assertEqual('200 OK', res.status)
        self.assertIn('application/json', res.headers['Content-Type'])
        self.assertIsNotNone(res.json['id'])
        self.assertEqual(res.json['type'], 'concept')

    def test_get_concept_not_found(self):
        res = self.testapp.get('/conceptschemes/TREES/c/89', headers=self._get_default_headers(), status=404,
                               expect_errors=True)
        self.assertEqual('404 Not Found', res.status)
        self.assertIn('application/json', res.headers['Content-Type'])

    def test_get_concept_dictprovider_not_found(self):
        res = self.testapp.get('/conceptschemes/TEST/c/89', headers=self._get_default_headers(), status=404,
                               expect_errors=True)
        self.assertEqual('404 Not Found', res.status)
        self.assertIn('application/json', res.headers['Content-Type'])

    def test_add_concept(self):
        res = self.testapp.post_json('/conceptschemes/TREES/c', headers=self._get_default_headers(), params=json_value)
        self.assertEqual('201 Created', res.status)
        self.assertIn('application/json', res.headers['Content-Type'])
        self.assertIsNotNone(res.json['id'])
        self.assertEqual(res.json['type'], 'concept')

    def test_add_concept_empty_conceptscheme(self):
        res = self.testapp.post_json('/conceptschemes/STYLES/c', headers=self._get_default_headers(),
                                     params=json_value)
        self.assertEqual('201 Created', res.status)
        self.assertIn('application/json', res.headers['Content-Type'])
        self.assertIsNotNone(res.json['id'])

    def test_add_concept_invalid_json(self):
        res = self.testapp.post_json(
            '/conceptschemes/TREES/c', headers=self._get_default_headers(), params=json_value_invalid, status=400)
        self.assertEqual('400 Bad Request', res.status)
        self.assertIn('application/json', res.headers['Content-Type'])

    def test_add_concept_conceptscheme_not_found(self):
        res = self.testapp.post_json(
            '/conceptschemes/GARDENNNN/c', headers=self._get_default_headers(), params=json_value, status=404,
            expect_errors=True)
        self.assertEqual('404 Not Found', res.status)
        self.assertIn('application/json', res.headers['Content-Type'])

    def test_edit_concept(self):
        res = self.testapp.put_json(
            '/conceptschemes/TREES/c/1', headers=self._get_default_headers(), params=json_value)
        self.assertEqual('200 OK', res.status)
        self.assertIn('application/json', res.headers['Content-Type'])

    def test_edit_concept_has_relations(self):
        res = self.testapp.put_json(
            '/conceptschemes/MATERIALS/c/13', headers=self._get_default_headers(), params=json_value_relations)
        self.assertEqual('200 OK', res.status)
        self.assertIn('application/json', res.headers['Content-Type'])
        self.assertEqual(2, len(res.json['narrower']))

    def test_edit_concept_not_found(self):
        res = self.testapp.put_json(
            '/conceptschemes/TREES/c/89', headers=self._get_default_headers(), params=json_value, status=404,
            expect_errors=True)
        self.assertEqual('404 Not Found', res.status)
        self.assertIn('application/json', res.headers['Content-Type'])

    def test_delete_concept(self):
        new_id = 1
        res = self.testapp.delete('/conceptschemes/TREES/c/' + str(new_id), headers=self._get_default_headers())
        self.assertEqual('200 OK', res.status)
        self.assertIsNotNone(res.json['id'])
        self.assertEqual(new_id, res.json['id'])

    def test_delete_concept_not_found(self):
        res = self.testapp.delete('/conceptschemes/TREES/c/7895', headers=self._get_default_headers(),
                                  expect_errors=True)
        self.assertEqual('404 Not Found', res.status)

    def test_add_collection(self):
        res = self.testapp.post_json('/conceptschemes/GEOGRAPHY/c', headers=self._get_default_headers(),
                                     params=json_collection_value)
        self.assertEqual('201 Created', res.status)
        self.assertIn('application/json', res.headers['Content-Type'])
        self.assertIsNotNone(res.json['id'])
        self.assertEqual(res.json['type'], 'collection')

    def test_edit_collection(self):
        json_collection_value['members'] = [{"id": 7}, {"id": 8}]
        res = self.testapp.put_json('/conceptschemes/GEOGRAPHY/c/333', headers=self._get_default_headers(),
                                    params=json_collection_value)
        self.assertEqual('200 OK', res.status)
        self.assertIn('application/json', res.headers['Content-Type'])
        self.assertIsNotNone(res.json['id'])
        self.assertEqual(res.json['type'], 'collection')
        self.assertEqual(2, len(res.json['members']))

    def test_delete_collection(self):
        res = self.testapp.delete('/conceptschemes/GEOGRAPHY/c/333', headers=self._get_default_headers())
        self.assertEqual('200 OK', res.status)
        self.assertIn('application/json', res.headers['Content-Type'])

    def test_uri(self):
        res = self.testapp.post_json('/conceptschemes/MATERIALS/c', headers=self._get_default_headers(),
                                     params=json_value)
        self.assertEqual('201 Created', res.status)
        self.assertIn('application/json', res.headers['Content-Type'])
        self.assertEqual('urn:x-vioe:materials:51', res.json['uri'])

    def test_general_exception_view(self):
        self.testapp.post_json('/conceptschemes/GEOGRAPHY/c', headers=self._get_default_headers(),
                               params=json_collection_value)
        res = self.testapp.put_json('/conceptschemes/GEOGRAPHY/c/1', headers=self._get_default_headers(),
                                    params=json_collection_value, expect_errors=True)
        self.assertEqual('500 Internal Server Error', res.status)
        self.assertIn("unexpected server error", res)

    def test_get_languages(self):
        res = self.testapp.get('/languages', headers=self._get_default_headers())
        self.assertEqual('200 OK', res.status)
        self.assertIn('application/json', res.headers['Content-Type'])
        self.assertIsNotNone(res)
        self.assertEqual(len(res.json), 3)

    def test_get_language(self):
        res = self.testapp.get('/languages/de', headers=self._get_default_headers())
        self.assertEqual('200 OK', res.status)
        self.assertIn('application/json', res.headers['Content-Type'])
        self.assertIsNotNone(res.json['id'])
        self.assertEqual(res.json['name'], 'test')

    def test_get_language_not_found(self):
        res = self.testapp.get('/languages/jos', headers=self._get_default_headers(), expect_errors=True)
        self.assertEqual('404 Not Found', res.status)
        self.assertIn('application/json', res.headers['Content-Type'])
        self.assertIsNotNone(res.json)
        self.assertEqual(res.json, {"message": "The resource could not be found."})

    def test_add_language(self):
        res = self.testapp.put_json('/languages/af', headers=self._get_default_headers(),
                                    params={"id": "af", "name": "Afrikaans"})
        self.assertEqual('200 OK', res.status)
        self.assertIn('application/json', res.headers['Content-Type'])
        self.assertIsNotNone(res.json['id'])
        self.assertEqual(res.json['name'], 'Afrikaans')

    def test_add_language_non_valid(self):
        res = self.testapp.put_json('/languages/flup', headers=self._get_default_headers(),
                                    params={"id": "flup", "name": "flup"}, expect_errors=True)
        self.assertEqual('400 Bad Request', res.status)
        self.assertIn('application/json', res.headers['Content-Type'])
        self.assertIsNotNone(res.json)
        self.assertEqual(res.json, {
            "errors": [{"id": "Invalid language tag: Unknown code 'flup', Missing language tag in 'flup'."}],
            "message": "Language could not be validated"})

    def test_add_language_non_valid_json(self):
        res = self.testapp.put_json('/languages/af', headers=self._get_default_headers(),
                                    params={"test": "flup"}, expect_errors=True)
        self.assertEqual('400 Bad Request', res.status)
        self.assertIn('application/json', res.headers['Content-Type'])
        self.assertIsNotNone(res.json)
        self.assertEqual(res.json, {'errors': {'name': 'Required'}, 'message': 'Language could not be validated'})

    def test_edit_language(self):
        res = self.testapp.put_json('/languages/de', headers=self._get_default_headers(),
                                    params={"id": "de", "name": "Duits"})
        self.assertEqual('200 OK', res.status)
        self.assertIn('application/json', res.headers['Content-Type'])
        self.assertIsNotNone(res.json['id'])
        self.assertEqual(res.json['name'], 'Duits')

    def test_edit_language_invalid_language_tag(self):
        res = self.testapp.put_json('/languages/joss', headers=self._get_default_headers(),
                                    params={"id": "joss", "name": "Duits"}, expect_errors=True)
        self.assertEqual('400 Bad Request', res.status)
        self.assertIn('application/json', res.headers['Content-Type'])
        self.assertIsNotNone(res.json)
        self.assertEqual(res.json, {
            'errors': [{'id': "Invalid language tag: Unknown code 'joss', Missing language tag in 'joss'."}]
            , "message": "Language could not be validated"})

    def test_edit_language_no_id(self):
        res = self.testapp.put_json('/languages/de', headers=self._get_default_headers(),
                                    params={"name": "Duits"})
        self.assertEqual('200 OK', res.status)
        self.assertIn('application/json', res.headers['Content-Type'])
        self.assertIsNotNone(res.json['id'])
        self.assertEqual(res.json['name'], 'Duits')

    def test_delete_language(self):
        res = self.testapp.delete('/languages/de', headers=self._get_default_headers())
        self.assertEqual('200 OK', res.status)
        self.assertIn('application/json', res.headers['Content-Type'])

    def test_delete_language_not_found(self):
        res = self.testapp.delete('/languages/jos', headers=self._get_default_headers(), expect_errors=True)
        self.assertEqual('404 Not Found', res.status)
        self.assertIn('application/json', res.headers['Content-Type'])
        self.assertIsNotNone(res.json)
        self.assertEqual(res.json, {"message": "The resource could not be found."})

    def test_delete_protected_resource(self):
        res = self.testapp.delete('/conceptschemes/GEOGRAPHY/c/9', headers=self._get_default_headers(),
                                  expect_errors=True)
        self.assertEqual('409 Conflict', res.status)
        self.assertIn('application/json', res.headers['Content-Type'])
        self.assertIsNotNone(res.json)
        self.assertEqual(res.json, {
            "message": "resource http://localhost/conceptschemes/GEOGRAPHY/c/9 is still in use, preventing operation",
            "referenced_in": ["urn:someobject", "http://test.test.org/object/2"]
        })


class TestCookieView(FunctionalTests):
    def _get_default_headers(self):
        return {'Accept': 'text/html'}

    def test_cookie(self):
        response = self.testapp.get('/locale?language=nl', headers=self._get_default_headers())
        self.assertIsNotNone(response.headers['Set-Cookie'])
        self.assertEqual(response.status, '302 Found')
        self.assertTrue((response.headers.get('Set-Cookie')).startswith('_LOCALE_=nl'))

    def test_unsupported_language(self):
        config_default_lang = settings.get('pyramid.default_locale_name')
        response = self.testapp.get('/locale?language=fr', headers=self._get_default_headers())
        self.assertTrue((response.headers.get('Set-Cookie')).startswith('_LOCALE_=' + config_default_lang))


class JsonTreeFunctionalTests(FunctionalTests):
    def _get_default_headers(self):
        return {'Accept': 'application/json'}

    def test_tree(self):
        response = self.testapp.get('/conceptschemes/MATERIALS/tree?_LOCALE_=nl', headers=self._get_default_headers())
        self.assertEqual('200 OK', response.status)
        self.assertIn('application/json', response.headers['Content-Type'])
        self.assertIsNotNone(response.json)
        self.assertEqual('Materiaal', response.json[0]['label'])

    def test_no_tree(self):
        response = self.testapp.get('/conceptschemes/FOO/tree?_LOCALE_=nl', headers=self._get_default_headers(),
                                    status=404, expect_errors=True)
        self.assertEqual('404 Not Found', response.status)


class SkosFunctionalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = engine_from_config(settings, prefix='sqlalchemy.')
        cls.session_maker = sessionmaker(
            bind=cls.engine,
            extension=ZopeTransactionExtension()
        )

    def setUp(self):
        self.config = Configurator(settings=settings)
        includeme(self.config)

        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)

        Base.metadata.bind = self.engine

        self.config.registry.dbmaker = self.session_maker
        self.config.add_request_method(db, reify=True)

        self.app = self.config.make_wsgi_app()
        self.testapp = TestApp(self.app)

    def tearDown(self):
        testing.tearDown()

    def _get_default_headers(self):
        return {'Accept': 'text/html'}

    def _get_json_headers(self):
        return {'Accept': 'application/json'}

    def test_admin_no_skos_provider(self):
        del self.app.request_extensions.descriptors['skos_registry']
        res = self.testapp.get('/admin', headers=self._get_default_headers(), expect_errors=True)
        self.assertEqual('500 Internal Server Error', res.status)
        self.assertTrue('message' in res)
        self.assertTrue('No SKOS registry found, please check your application setup' in res)

    def test_crud_no_skos_provider(self):
        del self.app.request_extensions.descriptors['skos_registry']
        res = self.testapp.post_json('/conceptschemes/GEOGRAPHY/c', headers=self._get_json_headers(),
                                     params=json_collection_value, expect_errors=True)
        self.assertEqual('500 Internal Server Error', res.status)
        self.assertTrue('message' in res)
        self.assertTrue('No SKOS registry found, please check your application setup' in res)


class CacheFunctionalTests(FunctionalTests):
    def _get_default_headers(self):
        return {'Accept': 'application/json'}

    def test_create_cache(self):
        # clear entire cache before start
        invalidate_cache_response = self.testapp.get('/admin/tree/invalidate')
        self.assertEqual('200 OK', invalidate_cache_response.status)

        tree_response = self.testapp.get('/conceptschemes/MATERIALS/tree?_LOCALE_=nl')
        self.assertEqual('200 OK', tree_response.status)
        self.assertIsNotNone(tree_response.json)

        cached_tree_response = self.testapp.get('/conceptschemes/MATERIALS/tree?_LOCALE_=nl')
        self.assertEqual('200 OK', cached_tree_response.status)
        self.assertIsNotNone(cached_tree_response.json)

        self.assertEqual(tree_response.json, cached_tree_response.json)

    def test_auto_invalidate_cache(self):
        # clear entire cache before start
        invalidate_cache_response = self.testapp.get('/admin/tree/invalidate')
        self.assertEqual('200 OK', invalidate_cache_response.status)

        tree_response = self.testapp.get('/conceptschemes/MATERIALS/tree?_LOCALE_=nl')
        cached_tree_response = self.testapp.get('/conceptschemes/MATERIALS/tree?_LOCALE_=nl')
        self.assertEqual(tree_response.json, cached_tree_response.json)

        delete_response = self.testapp.delete('/conceptschemes/MATERIALS/c/31', headers=self._get_default_headers())
        self.assertEqual('200 OK', delete_response.status)
        self.assertIsNotNone(delete_response.json['id'])

        tree_response2 = self.testapp.get('/conceptschemes/MATERIALS/tree?_LOCALE_=nl')
        self.assertNotEqual(tree_response.json, tree_response2.json)

        cached_tree_response2 = self.testapp.get('/conceptschemes/MATERIALS/tree?_LOCALE_=nl')
        self.assertEqual(tree_response2.json, cached_tree_response2.json)


class RdfFunctionalTests(FunctionalTests):
    def test_rdf_xml(self):
        rdf_response = self.testapp.get('/conceptschemes/MATERIALS/c.rdf')
        self.assertEqual('200 OK', rdf_response.status)
        self.assertEqual('application/rdf+xml', rdf_response.content_type)

    def test_rdf_turtle(self):
        ttl_response = self.testapp.get('/conceptschemes/MATERIALS/c.ttl')
        self.assertEqual('200 OK', ttl_response.status)
        self.assertEqual('text/turtle', ttl_response.content_type)


class ListFunctionalTests(FunctionalTests):
    def test_labeltypes_list(self):
        labeltypeslist_res = self.testapp.get('/labeltypes')
        self.assertEqual('200 OK', labeltypeslist_res.status)
        self.assertEqual('application/json', labeltypeslist_res.content_type)
        self.assertIsNotNone(labeltypeslist_res.json)
        self.assertEqual(3, len(labeltypeslist_res.json))

    def test_notetypes_list(self):
        labeltypeslist_res = self.testapp.get('/notetypes')
        self.assertEqual('200 OK', labeltypeslist_res.status)
        self.assertEqual('application/json', labeltypeslist_res.content_type)
        self.assertIsNotNone(labeltypeslist_res.json)