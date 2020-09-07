import logging
import logging.config
import os
import pathlib
import shutil
import sys
from argparse import ArgumentParser
from collections import Counter, defaultdict
from datetime import date, datetime
from time import ctime

logger = logging.getLogger(__name__)

LOGGING_CONF_FILENAME = "logging.conf"
SUPPORTED_GROUPINGS = {"year", "month", "date"}


def parse_args():
    parser = ArgumentParser("Utility to group and rename files by create date")
    parser.add_argument("-r", "--rootdir", help="Root directory containing photos to be relocated", default=os.getcwd())
    parser.add_argument("-t", "--targetdir", help="Directory to which to relocate photos in --root", default=os.path.join(os.getcwd(), "_sorted"))
    parser.add_argument("-g", "--groupby", help="Attribute by which to group photos in a single folder", choices=SUPPORTED_GROUPINGS, default="year")
    parser.add_argument("--rename", help="Specify whether to rename files to <date_fmt>[_idx], preserving file extensions", action="store_true", default=False)
    parser.add_argument("-df", "--dateformat", help="Format of the date portion of resulting file names. Follows datetime.date.strftime convention", default="%Y%m%d")
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

def get_createdate(filename):
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
    return datetime_obj

def get_year_month_day(datetime_obj):
    year = str(datetime_obj.year)
    month = str(datetime_obj.month).rjust(2, "0")
    day = str(datetime_obj.day).rjust(2, "0")
    return year, month, day

def construct_groups(rootdir, groupby):
    # filenames are guaranteed to be distinct because
    # we do not recursively search through rootdir
    groupsdict = defaultdict(list)
    for filename in os.listdir(rootdir):
        filepath = os.path.join(rootdir, filename)
        createdate = get_createdate(filepath)
        year, month, day = get_year_month_day(createdate)
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
            if os.path.isdir(filepath):
                continue
            shutil.copyfile(filepath, targetpath)
            shutil.copystat(filepath, targetpath)

def rename_files(targetdir, datefmt):
    """
    Apple "Live" photos will have 1 jpeg and 1 mov for each photo. They
    share a file name, but have different extensions. Renamed
    files reflect the same naming convention.
    """
    for groupname in os.listdir(targetdir):
        groupdir = os.path.join(targetdir, groupname)

        # construct mapping of each file name their extensions
        filename_exts = defaultdict(list)
        for filename in os.listdir(groupdir):
            file_ext = filename.split(".")[-1]
            filename_no_ext = filename.replace(f".{file_ext}", "")
            filename_exts[filename_no_ext].append(file_ext)

        # construct per-date file counts by extension-agnostic file name
        date_counts = Counter()
        for filename_no_ext, file_exts in filename_exts.items():
            # assign the indices here
            cur_filename = f"{filename_no_ext}.{file_exts[0]}"
            cur_filepath = os.path.join(groupdir, cur_filename)
            createdate = get_createdate(cur_filepath)
            createdate_dateinfo = get_year_month_day(createdate)
            date_counts[createdate_dateinfo] += 1

        # apply rename on filesystem
        seen_dates_counter = Counter()
        for filename_no_ext, file_exts in filename_exts.items():
            for i, file_ext in enumerate(file_exts):
                filename = f"{filename_no_ext}.{file_ext}"
                # rename each file to its formatted create date
                cur_filepath = os.path.join(groupdir, filename)
                createdate = get_createdate(cur_filepath)
                new_filename = createdate.strftime(datefmt)
                createdate_dateinfo = get_year_month_day(createdate)
                if date_counts[createdate_dateinfo] > 1:
                    # we only append idx if there is >1 file with same create date
                    if i == 0:
                        seen_dates_counter[createdate_dateinfo] += 1
                    idx = seen_dates_counter[createdate_dateinfo]
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
        logger.info(f"Renaming files to {opts.dateformat}[_idx] format...")
        rename_files(targetdir, opts.dateformat)

    logger.info("Completed successfully")
    return 0


if __name__ == "__main__":
    logger.setLevel(logging.INFO)
    log_config_path = os.path.join(pathlib.Path(__file__).parent.absolute(), LOGGING_CONF_FILENAME)
    logging.config.fileConfig(log_config_path, disable_existing_loggers=False)
    exitcode = main()
    sys.exit(exitcode)
