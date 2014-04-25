import colander
from pyramid.view import view_defaults, view_config
from sqlalchemy import func
from sqlalchemy.orm.exc import NoResultFound
from atramhasis.errors import InvalidJsonException, SkosRegistryNotFoundException, ConceptSchemeNotFoundException, \
    ValidationError, ConceptNotFoundException
from atramhasis.mappers import map_concept

from atramhasis.models import DBSession
from skosprovider_sqlalchemy.models import Concept, Thing
from atramhasis.utils import from_thing


@view_defaults(accept='application/json', renderer='skosjson')
class AtramhasisCrud(object):
    '''
    This object groups CRUD REST views part of the user interface.
    '''

    def __init__(self, request):
        self.request = request
        self.scheme_id = self.request.matchdict['scheme_id']
        if hasattr(request, 'skos_registry') and request.skos_registry is not None:
            self.skos_registry = self.request.skos_registry
        else:
            raise SkosRegistryNotFoundException()
        self.provider = self.skos_registry.get_provider(self.scheme_id)
        if not self.provider:
            raise ConceptSchemeNotFoundException(self.scheme_id)

    def _get_json_body(self):
        try:
            json_body = self.request.json_body
        except (ValueError, AttributeError) as e:
            raise InvalidJsonException()
        if 'id' in self.request.matchdict and not 'id' in json_body:
            json_body['id'] = self.request.matchdict['id']
        return json_body

    def _validate_concept(self, json_concept):
        from atramhasis.validators import (
            Concept as ConceptSchema,
        )

        concept_schema = ConceptSchema().bind(
            request=self.request
        )
        try:
            return concept_schema.deserialize(json_concept)
        except colander.Invalid as e:
            raise ValidationError(
                'Concept could not be validated',
                e.asdict()
            )

    @view_config(route_name='atramhasis.add_concept')
    def add_concept(self):
        validated_json_concept = self._validate_concept(self._get_json_body())
        cid = DBSession.query(
            func.max(Thing.concept_id)
        ).filter_by(conceptscheme_id=self.provider.conceptscheme_id).first()[0]
        if not cid:
            cid = 0
        cid += 1
        concept = Concept()
        concept.concept_id = cid
        concept.conceptscheme_id = self.provider.conceptscheme_id
        map_concept(concept, validated_json_concept)
        DBSession.add(concept)
        self.request.response.status = '201'
        self.request.response.location = self.request.route_path(
            'skosprovider.c', scheme_id=self.scheme_id, c_id=concept.concept_id)
        return from_thing(concept)

    @view_config(route_name='atramhasis.edit_concept')
    def edit_concept(self):
        c_id = self.request.matchdict['c_id']
        validated_json_concept = self._validate_concept(self._get_json_body())
        try:
            concept = DBSession.query(Concept).filter_by(concept_id=c_id).one()
        except NoResultFound:
            raise ConceptNotFoundException(c_id)
        map_concept(concept, validated_json_concept)
        self.request.response.status = '200'
        return from_thing(concept)

    @view_config(route_name='atramhasis.delete_concept')
    def delete_concept(self):
        c_id = self.request.matchdict['c_id']
        try:
            concept = DBSession.query(Concept).filter_by(concept_id=c_id).one()
        except NoResultFound:
            raise ConceptNotFoundException(c_id)
        DBSession.delete(concept)
        self.request.response.status = '200'
        return from_thing(concept)