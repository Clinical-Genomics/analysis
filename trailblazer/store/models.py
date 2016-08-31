# -*- coding: utf-8 -*-
from __future__ import division
import datetime
import json

import alchy
from sqlalchemy import Column, types, UniqueConstraint

STATUS_OPTIONS = ('pending', 'running', 'completed', 'failed', 'error')


def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, datetime.datetime):
        serial = obj.isoformat()
        return serial
    raise TypeError('Type not serializable')


class JsonModel(alchy.ModelBase):

    def to_json(self, pretty=False):
        """Serialize Model to JSON."""
        kwargs = dict(indent=4, sort_keys=True) if pretty else dict()
        return json.dumps(self.to_dict(), default=json_serial, **kwargs)


Model = alchy.make_declarative_base(Base=JsonModel)


class Metadata(Model):

    """Keep track of meta data."""

    id = Column(types.Integer, primary_key=True)
    created_at = Column(types.DateTime, default=datetime.datetime.now)
    updated_at = Column(types.DateTime)


class Analysis(Model):

    """Analysis record."""

    __table_args__ = (UniqueConstraint('case_id', 'started_at', 'status',
                                       'failed_step',
                                       name='_uc_case_start_status_step'),)

    id = Column(types.Integer, primary_key=True)
    case_id = Column(types.String(128))

    # metadata
    pipeline = Column(types.Enum('mip'))
    pipeline_version = Column(types.String(32))
    logged_at = Column(types.DateTime, default=datetime.datetime.now)
    started_at = Column(types.DateTime)
    completed_at = Column(types.DateTime)
    runtime = Column(types.Integer)
    cputime = Column(types.Integer)
    status = Column(types.Enum('pending', 'running', 'completed', 'failed'))
    root_dir = Column(types.Text)
    config_path = Column(types.Text)
    type = Column(types.Enum('exomes', 'genomes'))
    failed_step = Column(types.String(128), default='na')
    failed_at = Column(types.DateTime)
    comment = Column(types.Text)
    is_deleted = Column(types.Boolean, default=False)
    _samples = Column(types.Text)

    @property
    def samples(self):
        return self._samples.split(',') if self._samples else []

    @samples.setter
    def samples(self, sample_list):
        """Serialize a list of sample ids."""
        self._samples = ','.join(sample_list)

    @property
    def runtime_obj(self):
        """Format runtime as datetime object."""
        return datetime.timedelta(seconds=self.runtime)

    def failed_variantrecal(self):
        """Check if analysis failed on variat recalibration."""
        return (self.failed_step and
                'GATKVariantRecalibration' in self.failed_step)
