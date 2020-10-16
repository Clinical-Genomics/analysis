# -*- coding: utf-8 -*-
"""Store backend in Trailblazer"""
from typing import List, Optional
import datetime as dt
from pathlib import Path
import shutil

import alchy
from alchy import Query
import sqlalchemy as sqa

from trailblazer.constants import (
    STARTED_STATUSES,
    ONGOING_STATUSES,
    FAILED_STATUS,
    COMPLETED_STATUS,
)
from trailblazer.store import models
from trailblazer.exc import TrailblazerError


class BaseHandler:
    User = models.User
    Analysis = models.Analysis
    Job = models.Job
    Info = models.Info

    def setup(self):
        self.create_all()
        # add initial metadata record (for web interface)
        new_info = self.Info()
        self.add_commit(new_info)

    def info(self) -> models.Info:
        """Return metadata entry."""
        return self.Info.query.first()

    def set_latest_update_date(self):
        """
        used in CLI
        Update the latest updated date in the database."""
        metadata = self.info()
        metadata.updated_at = dt.datetime.now()
        self.commit()

    def get_analysis(self, case_id: str, started_at: dt.datetime, status: str) -> models.Analysis:
        """
        used in LOG
        Find a single analysis."""
        query = self.Analysis.query.filter_by(family=case_id, started_at=started_at, status=status)
        return query.first()

    def find_analyses_with_comment(self, comment: str) -> Query:
        """
        used in CLI
        Find a analyses containing comment."""
        analysis_query = self.Analysis.query

        analysis_query = analysis_query.filter(self.Analysis.comment.like(f"%{comment}%"))
        return analysis_query

    def aggregate_failed(self, since_when: dt.date = None) -> List[dict]:
        """
        used in FRONTEND
        Count the number of failed jobs per category (name)."""

        categories = self.session.query(
            self.Job.name.label("name"),
            sqa.func.count(self.Job.id).label("count"),
        ).filter(self.Job.status != "cancelled")

        if since_when:
            categories = categories.filter(self.Job.started_at > since_when)

        categories = categories.group_by(self.Job.name).all()

        data = [{"name": category.name, "count": category.count} for category in categories]
        return data

    def analyses(
        self,
        case_id: str = None,
        query: str = None,
        status: str = None,
        deleted: bool = None,
        temp: bool = False,
        before: dt.datetime = None,
        is_visible: bool = None,
        family: str = None,
    ) -> Query:
        """
        used by REST +> CG
        Fetch analyses from the database."""
        if not case_id:
            case_id = family

        analysis_query = self.Analysis.query
        if case_id:
            analysis_query = analysis_query.filter_by(family=case_id)
        elif query:
            analysis_query = analysis_query.filter(
                sqa.or_(
                    self.Analysis.family.like(f"%{query}%"),
                    self.Analysis.status.like(f"%{query}%"),
                )
            )
        if status:
            analysis_query = analysis_query.filter_by(status=status)
        if isinstance(deleted, bool):
            analysis_query = analysis_query.filter_by(is_deleted=deleted)
        if temp:
            analysis_query = analysis_query.filter(self.Analysis.status.in_(ONGOING_STATUSES))
        if before:
            analysis_query = analysis_query.filter(self.Analysis.started_at < before)
        if is_visible is not None:
            analysis_query = analysis_query.filter_by(is_visible=is_visible)
        return analysis_query.order_by(self.Analysis.started_at.desc())

    def analysis(self, analysis_id: int) -> Optional[models.Analysis]:
        """
        used by REST
        Get a single analysis by id."""
        return self.Analysis.query.get(analysis_id)

    def get_latest_analysis(self, case_id: str) -> Optional[models.Analysis]:
        latest_analysis = self.analyses(case_id=case_id).first()
        return latest_analysis

    def get_latest_analysis_status(self, case_id: str) -> str:
        """Get latest analysis status for a case_id"""
        latest_analysis = self.get_latest_analysis(case_id=case_id)
        if latest_analysis:
            return latest_analysis.status

    def is_latest_analysis_ongoing(self, case_id: str) -> bool:
        """Check if the latest analysis is ongoing for a case_id"""
        latest_analysis_status = self.get_latest_analysis_status(case_id=case_id)
        if latest_analysis_status in ONGOING_STATUSES:
            return True
        return False

    def is_latest_analysis_failed(self, case_id: str) -> bool:
        """Check if the latest analysis is failed for a case_id"""
        latest_analysis_status = self.get_latest_analysis_status(case_id=case_id)
        if latest_analysis_status == FAILED_STATUS:
            return True
        return False

    def is_latest_analysis_completed(self, case_id: str) -> bool:
        """Check if the latest analysis is completed for a case_id"""
        latest_analysis = self.analyses(case_id=case_id).first()
        if latest_analysis and latest_analysis.status == COMPLETED_STATUS:
            return True
        return False

    def has_latest_analysis_started(self, case_id: str) -> bool:
        """Check if analysis has started"""
        latest_analysis_status = self.get_latest_analysis_status(case_id=case_id)
        if latest_analysis_status in STARTED_STATUSES:
            return True
        return False

    def add_pending_analysis(self, case_id: str, email: str = None) -> models.Analysis:
        """Add pending entry for an analysis."""
        started_at = dt.datetime.now()
        new_log = self.Analysis(family=case_id, status="pending", started_at=started_at)
        new_log.user = self.user(email) if email else None
        self.add_commit(new_log)
        return new_log

    def add_user(self, name: str, email: str) -> models.User:
        """Add a new user to the database."""
        new_user = self.User(name=name, email=email)
        self.add_commit(new_user)
        return new_user

    def user(self, email: str) -> models.User:
        """Fetch a user from the database."""
        return self.User.query.filter_by(email=email).first()

    def jobs(self):
        """Return all jobs in the database."""
        return self.Job.query

    def mark_analyses_deleted(self, case_id: str) -> Query:
        """ mark analyses connected to a case as deleted """
        old_analyses = self.analyses(case_id=case_id)
        if old_analyses.count() > 0:
            for old_analysis in old_analyses:
                old_analysis.is_deleted = True
        self.commit()
        return old_analyses

    def delete_analysis(self, analysis_id: int, force: bool = False) -> None:
        """Delete the analysis output."""
        analysis_obj = self.analysis(analysis_id=analysis_id)
        if not analysis_obj:
            raise TrailblazerError("Analysis not found")
        if not force and self.analyses(case_id=analysis_obj.family, temp=True).count() > 0:
            raise TrailblazerError(
                f"Analysis for {analysis_obj.family} is currently running! Use --force flag to delete anyway."
            )
        if analysis_obj.out_dir:
            analysis_path = Path(analysis_obj.out_dir).parent
            if analysis_path.is_dir():
                shutil.rmtree(analysis_path, ignore_errors=True)
        analysis_obj.delete()
        self.mark_analyses_deleted(case_id=analysis_obj.family)


class Store(alchy.Manager, BaseHandler):
    def __init__(self, uri: str, families_dir: str):
        super(Store, self).__init__(config=dict(SQLALCHEMY_DATABASE_URI=uri), Model=models.Model)
        self.families_dir = families_dir
