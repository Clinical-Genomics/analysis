# -*- coding: utf-8 -*-
import logging
import signal
import subprocess

from trailblazer.exc import MipStartError

LOG = logging.getLogger(__name__)

CLI_OPTIONS = {
    'config': {'option': '--config_file'},
    'priority': {'option': '--slurm_quality_of_service'},
    'email': {'option': '--email'},
    'base': {'option': '--cluster_constant_path'},
    'dryrun': {'option': '--dry_run_all'},
    'gene_list': {'option': '--vcfparser_slt_fl'},
    'max_gaussian': { 'option': '--gatk_varrecal_snv_max_gau'},
    'skip_evaluation': {'option': '--qccollect_skip_evaluation'},
    'start_with': {'option': '--start_with_recipe'},
}


class MipCli(object):

    """Wrapper around MIP command line interface."""

    def __init__(self, script, pipeline):
        """Initialize MIP command line interface."""
        self.script = script
        self.pipeline = pipeline

    def __call__(self, config, case, **kwargs):
        """Execute the pipeline."""
        command = self.build_command(case, config, **kwargs)
        LOG.debug(' '.join(command))
        process = self.execute(command)
        process.wait()
        if process.returncode != 0:
            raise MipStartError('error starting analysis, check the output')
        return process

    def build_command(self, case, config, **kwargs):
        """Builds the command to execute MIP."""
        command = [self.script, self.pipeline, case, CLI_OPTIONS['config']['option'], config]
        print(command)
        for key, value in kwargs.items():
            # enable passing in flags as "False" - shouldn't add command
            if value:
                command.append(CLI_OPTIONS[key]['option'])

                # append value for non-flags
                if value is not True:
                    command.append(value)
        return command

    def execute(self, command):
        """Start a new MIP run."""

        """
        Remove the default SIGPIPE handler
        https://blog.nelhage.com/2010/02/a-very-subtle-bug/
        """
        process = subprocess.Popen(
            command,
            preexec_fn=lambda: signal.signal(signal.SIGPIPE, signal.SIG_DFL)
        )
        return process
