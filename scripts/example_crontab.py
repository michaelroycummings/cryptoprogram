## External Libraries
from crontab import CronTab
from pathlib import Path

def set_cron_tasks():
    '''
    Template for a function that would set cron tasks
    for functions that need to be run periodically.
    '''
    cron = CronTab(user='ec2-user')

    ## Create Job: ExampleJob1
    program_parent_folder_location = ''
    path_from_parent_to_examplejob1_script = ''

    job_comment = ''
    job_command = f'cd {Path(program_parent_folder_location)} && python3 -m {Path(path_from_parent_to_examplejob1_script)}'

    if job_comment not in [job.comment for job in cron]: # stops creation of duplicates of the same job
        ## Function run every 3 minutes for all hours of the day except 23:00
        job = cron.new(comment=job_comment, command=job_command)
        job.setall('*/3 0-22 * * *')
        cron.write()
        ## Function run every 3 minutes for 23:00, but not function run for the last 6 minutes of the day (for any resets necessary)
        job = cron.new(comment=job_comment, command=job_command)
        job.setall('0,3,6,9,12,15,18,21,24,27,30,33,36,39,42,45,48,51,54 23 * * *')  # leaves 6 min for last job to complete
        cron.write()

    ## Create Job: ExampleJob2
    pass

    return