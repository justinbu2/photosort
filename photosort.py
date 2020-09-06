import logging
import logging.config
import os
import pathlib
import shutil
import sys
from argparse import ArgumentParser
from collections import Counter, defaultdict
from datetime import datetime
from time import ctime

logger = logging.getLogger(__name__)

LOGGING_CONF_NAME = "logging.conf"
SUPPORTED_GROUPINGS = {"year", "month", "date"}


def get_createdate_info(filename):
    """
    Returns the year, month, and day of the create date of
    `filename`.
    N.B. Results are integer strings (month and day are padded)
    """
    stat = os.stat(filename)
    create_date = stat.st_birthtime
    create_date_ctime = ctime(create_date)
    _, month, day, _, year = create_date_ctime.split()
    datetime_obj = datetime.strptime(f"{year} {month} {day}", "%Y %b %d")
    year = str(datetime_obj.year)
    month = str(datetime_obj.month).rjust(2, "0")
    day = str(datetime_obj.day).rjust(2, "0")
    return year, month, day

def parse_args():
    parser = ArgumentParser("Utility to group and rename files by create date")
    parser.add_argument("-r", "--rootdir", help="Root directory containing photos to be relocated", default=os.getcwd())
    parser.add_argument("-t", "--targetdir", help="Directory to which to relocate photos in --root", default=os.path.join(os.getcwd(), "_reorged"))
    parser.add_argument("-g", "--groupby", help="Attribute by which to group photos in a single folder", choices=SUPPORTED_GROUPINGS, default="year")
    parser.add_argument("--rename", help="Specify whether to rename files to YYYY-MM-DD[_idx], preserving file extensions", action="store_true", default=False)
    return parser.parse_args()

def validate_filenames(rootdir):
    error_filepaths = []
    for filename in os.listdir(rootdir):
        filepath = os.path.join(rootdir, filename)
        if os.path.isdir(filepath):
            logger.warning(f"Directory {filepath} will be ignored.")
            continue
        if "." not in filename:
            error_filepaths.append(filepath)
    if error_filepaths:
        message = "The following files have errors. No files have been touched.\n"
        message += "\n".join(error_filepaths)
        raise Exception(message)

def construct_groups(rootdir, groupby):
    # filenames are guaranteed to be distinct because
    # we do not recursively search through rootdir
    groupsdict = defaultdict(list)
    for filename in os.listdir(rootdir):
        year, month, day = get_createdate_info(filename)
        if groupby == "year":
            groupname = year
        elif groupby == "month":
            groupname = f"{year}-{month}"
        elif groupby == "date":
            groupname = f"{year}-{month}-{day}"
        else:
            raise Exception(f"Unsupported group: {groupby}")
        groupsdict[groupname].append(filename)
    return groupsdict

def copy_files(groupsdict, rootdir, targetdir):
    for groupname, groupfiles in groupsdict.items():
        for filename in groupfiles:
            # copy to group's folder
            targetgroup_dir = os.path.join(targetdir, groupname)
            if not os.path.exists(targetgroup_dir):
                os.makedirs(targetgroup_dir)
            targetpath = os.path.join(targetgroup_dir, filename)
            filepath = os.path.join(rootdir, filename)
            shutil.copyfile(filepath, targetpath)
            shutil.copystat(filepath, targetpath)

def rename_files(targetdir):
    for groupname in os.listdir(targetdir):
        groupdir = os.path.join(targetdir, groupname)
        # construct counter. we only append idx if there are >1 file with same create date
        file_dates = [get_createdate_info(os.path.join(groupdir, filename)) for filename in os.listdir(groupdir)]
        date_counts = Counter(file_dates)
        seen_dates_counter = defaultdict(int)
        for filename in os.listdir(groupdir):
            # rename each file to its create date
            cur_filepath = os.path.join(groupdir, filename)
            createdate_info = get_createdate_info(cur_filepath)
            year, month, day = createdate_info
            create_date_str = "-".join([year, month, day])
            new_filename = create_date_str
            if date_counts[createdate_info] > 1:
                seen_dates_counter[createdate_info] += 1
                idx = seen_dates_counter[createdate_info]
                new_filename = f"{new_filename}_{idx}"
            file_ext = filename.split(".")[-1]
            new_filename_w_ext = f"{new_filename}.{file_ext}"

            new_targetpath = os.path.join(groupdir, new_filename_w_ext)
            os.rename(cur_filepath, new_targetpath)

def main():
    opts = parse_args()
    rootdir = os.path.expanduser(opts.rootdir)
    targetdir = os.path.expanduser(opts.targetdir)

    # validate file names
    validate_filenames(rootdir)

    # construct groups
    logger.info("Constructing groups...")
    groupsdict = construct_groups(rootdir, opts.groupby)

    # copy to group dirs
    logger.info("Copying files to group folders...")
    copy_files(groupsdict, rootdir, targetdir)

    # renaming files
    if opts.rename:
        logger.info("Renaming files to yyyy-mm-dd[_idx] format...")
        rename_files(targetdir)

    logger.info("Completed successfully")
    return 0


if __name__ == "__main__":
    logger.setLevel(logging.INFO)
    log_config_path = os.path.join(pathlib.Path(__file__).parent.absolute(), LOGGING_CONF_NAME)
    logging.config.fileConfig(log_config_path, disable_existing_loggers=False)
    exitcode = main()
    sys.exit(exitcode)
