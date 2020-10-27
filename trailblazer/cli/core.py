import logging

import click
import coloredlogs
import ruamel.yaml
from dateutil.parser import parse as parse_date

import trailblazer
from trailblazer.store import Store
from trailblazer.store.models import STATUS_OPTIONS

LOG = logging.getLogger(__name__)


@click.group()
@click.option("-c", "--config", type=click.File())
@click.option("-d", "--database", help="path/URI of the SQL database")
@click.option("-l", "--log-level", default="INFO")
@click.version_option(trailblazer.__version__, prog_name=trailblazer.__title__)
@click.pass_context
def base(context, config, database, log_level):
    """Trailblazer - Simplify running MIP!"""
    coloredlogs.install(level=log_level)

    context.obj = ruamel.yaml.safe_load(config) if config else {}
    context.obj["database"] = database or context.obj.get("database")
    context.obj["trailblazer"] = Store(context.obj["database"])


@base.command()
@click.option("--reset", is_flag=True, help="reset database before setting up tables")
@click.option("--force", is_flag=True, help="bypass manual confirmations")
@click.pass_context
def init(context, reset, force):
    """Setup the database."""
    existing_tables = context.obj["trailblazer"].engine.table_names()
    if force or reset:
        if existing_tables and not force:
            message = f"Delete existing tables? [{', '.join(existing_tables)}]"
            click.confirm(click.style(message, fg="yellow"), abort=True)
        context.obj["trailblazer"].drop_all()
    elif existing_tables:
        LOG.warning("Database already exists, use '--reset'")
        context.abort()
    context.obj["trailblazer"].setup()
    LOG.info(f"Success! New tables: {', '.join(context.obj['trailblazer'].engine.table_names())}")


@base.command()
@click.pass_context
def scan(context):
    """Scan a directory for analyses."""
    context.obj["trailblazer"].update_ongoing_analyses()
    LOG.info("Analyses updated!")


@base.command()
@click.pass_context
def update_analysis(context, analysis_id: int):
    """Scan a directory for analyses."""
    context.obj["trailblazer"].update_run_status(analysis_id)
    LOG.info(f"Analysis {analysis_id} updated!")


@base.command()
@click.option("--name", help="Name of new user to add")
@click.argument("email")
@click.pass_context
def user(context, name, email):
    """Add a new or display information about an existing user."""
    existing_user = context.obj["trailblazer"].user(email)
    if existing_user:
        LOG.info(f"Existing user found: {existing_user.to_dict()}")
    elif name:
        new_user = context.obj["trailblazer"].add_user(name, email)
        LOG.info(f"New user added: {email} ({new_user.id})")
    else:
        LOG.error("User not found")


@base.command()
@click.argument("analysis_id", type=int)
@click.pass_context
def cancel(context, analysis_id):
    """Cancel all jobs in a run."""
    try:
        context.obj["trailblazer"].cancel_analysis(analysis_id=analysis_id)
    except Exception as e:
        LOG.error(e)


@base.command()
@click.option("--force", is_flag=True, help="Force delete if analysis ongoing")
@click.argument("analysis_id", type=int)
@click.pass_context
def delete(context, analysis_id: int, force: bool):
    try:
        context.obj["trailblazer"].delete_analysis(analysis_id=analysis_id, force=force)
    except Exception as e:
        LOG.error(e)


@base.command("ls")
@click.option(
    "-s", "--status", type=click.Choice(STATUS_OPTIONS), help="Find analysis with specified status"
)
@click.option("-b", "--before", help="Find analyses started before date")
@click.option("-c", "--comment", help="Find analysis with comment")
@click.pass_context
def ls_cmd(context, before, status, comment):
    """Display recent logs for analyses."""
    runs = (
        context.obj["trailblazer"]
        .analyses(
            status=status,
            deleted=False,
            before=parse_date(before) if before else None,
            comment=comment,
        )
        .limit(30)
    )
    for run_obj in runs:
        if run_obj.status == "pending":
            message = f"{run_obj.id} | {run_obj.family} [{run_obj.status.upper()}]"
        else:
            message = (
                f"{run_obj.id} | {run_obj.family} {run_obj.started_at.date()} "
                f"[{run_obj.type.upper()}/{run_obj.status.upper()}]"
            )
            if run_obj.status == "running":
                message = click.style(f"{message} - {run_obj.progress * 100}/100", fg="blue")
            elif run_obj.status == "completed":
                message = click.style(f"{message} - {run_obj.completed_at}", fg="green")
            elif run_obj.status == "failed":
                message = click.style(message, fg="red")
        click.echo(message)
