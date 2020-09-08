import logging
import logging.config
import math
import os
import pathlib
import shutil
import sys
from argparse import ArgumentParser
from collections import Counter, OrderedDict, defaultdict
from datetime import datetime
from time import ctime

logger = logging.getLogger(__name__)

LOGGING_CONF_FILENAME = "logging.conf"
SUPPORTED_GROUPINGS = {"year", "month", "date"}
IGNORED_FILENAMES = {".DS_Store"}


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

def get_files_createdates(rootdir):
    """
    Return mapping of `rootdir`'s files to their respective create dates,
    sorted by ascending create date. Ignores directories.
    """
    rootdir_filepaths = [
        os.path.join(rootdir, f)
        for f in os.listdir(rootdir)
        if not os.path.isdir(f) and f not in IGNORED_FILENAMES]
    filepath_createdate_pairs = [(filepath, get_createdate(filepath)) for filepath in rootdir_filepaths]
    return OrderedDict(sorted(filepath_createdate_pairs, key=lambda elem: elem[1]))

def get_createdate(filename):
    epoch_createtime = get_epoch_createtime(filename)
    _, month, day, time, year = epoch_createtime.split()
    datetime_obj = datetime.strptime(f"{year} {month} {day} {time}", "%Y %b %d %H:%M:%S")
    return datetime_obj

def get_epoch_createtime(filename):
    stat = os.stat(filename)
    create_date = stat.st_birthtime
    epoch_createtime = ctime(create_date)
    return epoch_createtime

def get_year_month_day(datetime_obj):
    year = str(datetime_obj.year)
    month = str(datetime_obj.month).rjust(2, "0")
    day = str(datetime_obj.day).rjust(2, "0")
    return year, month, day

def construct_groups(files_createdates_dict, groupby):
    """
    Construct mapping of groupname -> [filepaths]
    """
    groups_dict = defaultdict(list)
    for filepath, createdate in files_createdates_dict.items():
        year, month, day = get_year_month_day(createdate)
        if groupby == "year":
            groupname = year
        elif groupby == "month":
            groupname = f"{year}-{month}"
        elif groupby == "date":
            groupname = f"{year}-{month}-{day}"
        else:
            raise Exception(f"Unsupported group: {groupby}")
        groups_dict[groupname].append(filepath)
    return groups_dict

def construct_copy_mapping(groups_dict, targetdir):
    """
    Construct mapping of root file path -> target file path,
    based on groups assigned in `groups_dict`
    """
    copy_dict = {}
    for groupname, group_filepaths in groups_dict.items():
        for filepath in group_filepaths:
            targetgroup_dir = os.path.join(targetdir, groupname)
            filename = filepath.split(os.path.sep)[-1]
            targetpath = os.path.join(targetgroup_dir, filename)
            copy_dict[filepath] = targetpath
    return copy_dict

def rename_copy_dict(copy_dict, files_createdates_dict, datefmt):
    """
    @param copy_dict: mapping of {root_filepath: target_filepath}
    @param files_createdates_dict: ordered mapping of {root_file_path: createdate}
    @param datefmt: string format of the date to use in target filenames
    @return: copy_dict, except with target file names renamed to formatted file dates
    """
    # construct per-date file counts by file path
    date_counts = Counter([get_year_month_day(cdate_obj) for cdate_obj in files_createdates_dict.values()])

    # construct dict of old name -> new name
    # note that for Apple Live photos, the resulting file names in the target dir will be different
    # eg. IMG_0001.jpeg -> targetdir/groupname/YYYYMMDD_1.jpeg
    #     IMG_0001.mov  -> targetdir/groupname/YYYYMMDD_2.mov
    renamed_copy_dict = {}
    seen_dates_counter = Counter()
    for filepath, createdate_obj in files_createdates_dict.items():
        new_filename = createdate_obj.strftime(datefmt)
        createdate_ymd = get_year_month_day(createdate_obj)
        createdate_count = date_counts[createdate_ymd]
        if createdate_count > 1:
            # we only append idx if there is >1 file with same create date
            seen_dates_counter[createdate_ymd] += 1
            # pad index if >10 distinct files with same create date.
            createdate_count_numdigits = int(math.log10(createdate_count)) + 1
            idx = str(seen_dates_counter[createdate_ymd]).rjust(createdate_count_numdigits, "0")
            new_filename = f"{new_filename}_{idx}"
        file_ext = filepath.split(".")[-1]
        new_filename = f"{new_filename}.{file_ext}"
        target_filepath = copy_dict[filepath]
        target_dir = os.path.sep.join(target_filepath.split(os.path.sep)[:-1])
        new_filepath = os.path.join(target_dir, new_filename)
        renamed_copy_dict[filepath] = new_filepath
    return renamed_copy_dict

def copy_files(copy_dict):
    """
    Copy files from paths specified in keys of dict to paths
    specified in values of dict. Does not overwrite files in
    target location if they already exist. Instead, we return
    them as a list for caller to use.
    """
    pre_existing_files = []
    for cur_filepath, target_filepath in copy_dict.items():
        target_dir = os.path.dirname(target_filepath)
        if not os.path.isdir(target_dir):
            os.makedirs(target_dir)
        if os.path.exists(target_filepath):
            pre_existing_files.append((cur_filepath, target_filepath))
            # do not overwrite file if target file already exists
            continue
        shutil.copyfile(cur_filepath, target_filepath)
        shutil.copystat(cur_filepath, target_filepath)
    return pre_existing_files

def roll_back(copy_dict, pre_existing_files):
    for target_path in copy_dict.values():
        if not os.path.exists(target_path) or target_path in pre_existing_files:
            continue
        os.remove(target_path)


def main():
    opts = parse_args()
    rootdir = os.path.expanduser(opts.rootdir)
    targetdir = os.path.expanduser(opts.targetdir)

    # validate file names
    validate_filenames(rootdir)

    # dict of filepath -> create datetime object, sorted by create date
    files_createdates_dict = get_files_createdates(rootdir)

    # construct groups
    logger.info("Constructing groups...")
    groups_dict = construct_groups(files_createdates_dict, opts.groupby)

    # construct dict of root paths to target paths
    logger.info("Constructing copy mapping from rootdir to targetdir...")
    copy_dict = construct_copy_mapping(groups_dict, targetdir)

    # renaming files
    if opts.rename:
        logger.info(f"Updating copy mapping to rename files to {opts.dateformat}[_idx] format...")
        copy_dict = rename_copy_dict(copy_dict, files_createdates_dict, opts.dateformat)

    # apply the copy of files over to targetdir
    logger.info(f"Copying files from {opts.rootdir} to {opts.targetdir}...")
    pre_existing_files = copy_files(copy_dict)
    if pre_existing_files:
        fmtted_pre_existing_files = "\n".join([f"{pair[0]} -> {pair[1]}" for pair in pre_existing_files])
        msg = f"Failed to write to following files. Rolling back all copied files.\n{fmtted_pre_existing_files}"
        logger.error(msg)
        roll_back(copy_dict, pre_existing_files)
        return 1

    logger.info("Completed successfully")
    return 0


if __name__ == "__main__":
    logger.setLevel(logging.INFO)
    log_config_path = os.path.join(pathlib.Path(__file__).parent.absolute(), LOGGING_CONF_FILENAME)
    logging.config.fileConfig(log_config_path, disable_existing_loggers=False)
    exitcode = main()
    sys.exit(exitcode)
