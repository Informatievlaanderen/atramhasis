# -*- coding: utf-8 -*-
"""
Module containing errors generated by Atramhasis.
"""

from pyramid.httpexceptions import HTTPNotFound


class SkosRegistryNotFoundException(Exception):
    """
    Atramhasis could not find a SKOS registry.
    """
    def __init__(self, value='No SKOS registry found, please check your application setup'):
        self.value = value

    def __str__(self):
        return repr(self.value)


class ConceptSchemeNotFoundException(HTTPNotFound):
    """
    A ConceptScheme could not be found.
    """
    def __init__(self, scheme_id):
        self.value = 'No conceptscheme found with the given id ' + scheme_id

    def __str__(self):
        return repr(self.value)


class LanguageNotFoundException(HTTPNotFound):
    """
    A Language could not be found.
    """
    def __init__(self, scheme_id):
        self.value = 'No language found with the given id ' + scheme_id

    def __str__(self):
        return repr(self.value)


class ConceptNotFoundException(HTTPNotFound):
    """
    A Concept or Collection could not be found.
    """
    def __init__(self, c_id):
        self.value = 'No concept found with the given id ' + c_id

    def __str__(self):
        return repr(self.value)


class ValidationError(Exception):
    """
    Some data that was validated is invalid.
    """
    def __init__(self, value, errors):
        self.value = value
        self.errors = errors

    def __str__(self):
        return repr(self.value)


class DbNotFoundException(Exception):
    """
    Atramhasis could not find a database.
    """
    def __init__(self, value='No database found, please check your application setup'):
        self.value = value

    def __str__(self):
        return repr(self.value)
