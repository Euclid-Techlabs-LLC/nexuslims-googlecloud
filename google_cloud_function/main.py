import json
import logging
import os
import tempfile

import hyperspy.api_nogui as hs
from google.cloud import storage
from PIL import Image

from nexuslims.meta.extractors import EXT_READER_MAP, PLACEHOLDER_PREVIEW
from nexuslims.meta.extractors.thumbnail_generator import (
    down_sample_image,
    sig_to_thumbnail
)

logger = logging.getLogger(__name__)
storage_client = storage.Client()


def generate_image_thumbnail_metafile(data, context):
    file_data = data

    file_name = file_data["name"]
    bucket_name = file_data["bucket"]

    blob = storage_client.bucket(bucket_name).get_blob(file_name)
    p, ext = os.path.splitext(file_name)
    _, tmp_image_filename = tempfile.mkstemp(suffix=ext)

    # download file from bucket
    blob.download_to_filename(tmp_image_filename)
    logger.debug(f"Image {file_name} was downloaded to {tmp_image_filename}.")

    # target bucket, make one if one does not exist
    target_bucket_name = f"{bucket_name}_meta"
    if not storage_client.lookup_bucket(target_bucket_name):
        logger.info(f"meta bucket: {target_bucket_name} does not exist,"
                    " creating one and make it public.")
        bucket = storage_client.create_bucket(target_bucket_name)
        bucket.make_public(recursive=True, future=True)
    target_bucket = storage_client.bucket(target_bucket_name)

    # generate and upload thumbnail
    _, tmp_thumbnail_filename = tempfile.mkstemp(suffix=".png")
    __generate_thumbnail(tmp_image_filename, tmp_thumbnail_filename)
    thumbnail_blob = target_bucket.blob(f"{p}.png")
    thumbnail_blob.upload_from_filename(tmp_thumbnail_filename)
    logger.info(f"Thumbnail {p}.png was generated for {file_name}.")

    # generate and upload metafile
    _, tmp_meta_filename = tempfile.mkstemp(suffix=".json")
    __generate_metafile(tmp_image_filename, tmp_meta_filename, blob.metadata)
    metafile_blob = target_bucket.blob(f"{p}.json")
    metafile_blob.upload_from_filename(tmp_meta_filename)
    logger.info(f"Metafile {p}.json was generated for {file_name}.")

    # delete temporary file
    os.remove(tmp_thumbnail_filename)
    os.remove(tmp_meta_filename)
    os.remove(tmp_image_filename)


def __generate_thumbnail(image_filename, thumbnail_filename):
    _, ext = os.path.splitext(image_filename)
    if ext == ".tif":
        down_sample_image(
            image_filename, out_path=thumbnail_filename, factor=2)
        return

    load_options = {'lazy': True}
    if ext == '.ser':
        load_options['only_valid_data'] = True

    try:
        s = hs.load(image_filename, **load_options)

        # If s is a list of signals, use just the first one for our purposes
        if isinstance(s, list):
            N = len(s)
            orig_name = s[0].metadata.General.original_filename
            s = s[0]
            more_text = f' (1 of {N} total signals in file "{orig_name}")'
            s.metadata.General.title += more_text
        elif s.metadata.General.title == '':
            title = s.metadata.General.original_filename.replace(ext, '')
            s.metadata.General.title = title

        s.compute(show_progressbar=False)
        sig_to_thumbnail(s, out_path=thumbnail_filename)
    except Exception:
        logger.warning('Signal could not be loaded by HyperSpy. '
                       'Using placeholder image for preview.')
        Image.open(PLACEHOLDER_PREVIEW).copy().save(thumbnail_filename)


def __generate_metafile(image_filename, meta_filename, extra):
    _, ext = os.path.splitext(image_filename)
    nx_meta = {}
    if ext in EXT_READER_MAP:
        EXT_READER_MAP[ext](image_filename, extra=extra)
    else:
        logger.warning(
            f'file type ({ext}) not supported for metadata extraction,'
            ' will return empty.'
        )

    if nx_meta and "DatasetType" not in nx_meta["nx_meta"]:
        nx_meta['nx_meta']['DatasetType'] = 'Misc'
        nx_meta['nx_meta']['Data Type'] = 'Miscellaneous'

    with open(meta_filename, 'w') as outf:
        outf.write(json.dumps(nx_meta))
