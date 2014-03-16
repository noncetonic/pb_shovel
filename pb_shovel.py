from sys import stderr
import os
import re
import argparse
import json
import requests

#
#   Title:  pb_shovel.py
#   Author: Daxda
#   Date:   15.03.1337 (time travel is possible bitches)
#   Desc:   This script extracts the images on the image hosting site 'Photobucket'
#           you pass either a single url with the -u/--url flag which points to
#           either an album or a single image, the script then will extract the
#           direct links to the image and saves it under a custom path which you
#           can specify with the -o/--output-directory flag, when this argument
#           is not defined the output directory will fall back to the current
#           working directory.
#
#           This project originates not from myself, but my dear friend Kulverstukas
#           he came up with the idea and asked me if I could rewrite, his now outdated,
#           scraper. I gladly accepted and here we are! You should check out his
#           website, he has lots of interessting projects going on, http://9v.lt/blog/
#
#
#   A short explanation how the program works:
#   First the class parses the arguments passed to it, the 'extract' method then
#   reads the file (if it was defined inside the arguments). The method then
#   iterates over each link (or just the one link defined with the -u/--url arg),
#   the links get passed to the method '_is_album' which tries to detect if the
#   passed link is pointing to an album or just a single link, the method's return
#   value is of type bool, it gets checked for and calls the correct routine for
#   the type of link. Ones the type is detected the '_get_source' method is called
#   to obtain the source of the link/s, the extracted source gets filtered with
#   regex for the image information. The image information then gets parsed with
#   json, the information gets stored inside 'ImageInfo' objects.
#
#   After all links have been visited the method 'download_all_files' or 'download_file'
#   is called, the first method iterates over all collected imageinfo objects
#   and passes them to the 'download_file' method, which extracts the image url
#   from the passed imageinfo object and downloads it.
#

class ImageInfo(object):
    """ Stores image attributes, the following attributes are stored:

            - Filename
            - Title
            - Link
            - Filetype
            - Like count
            - Comment count
            - View count
            - Username (the uploader of the file)
    """
    def __init__(self, filename, title, link, type_, likeCount, commentCount,
                 viewCount, username):
        self.filename = filename
        self.title = title
        self.link = link
        self.media_type = type_
        self.like_count = likeCount
        self.comment_count = commentCount
        self.view_count = viewCount
        self.username = username


class Photobucket():
    """ Scrapes the well known image hosting site Photobucket, either whole albums
        or single images. """
    def __init__(self, args):
        self._args = args
        self._downloaded_images = 0
        self._collected_images = []

    def extract(self):
        """ Starts the whole extraction process. """
        if(self._args.file):
            try: # Open the file the user passed with the -f/--file arg
                with open(self._args.file) as f:
                    links = [line.strip() for line in f.readlines() if line]
            except(IOError):
                stderr.write("Failed to open the specified file!\n")
                stder.flush()
                return
        else:
            links = (self._args.url, )

        self._collected_links = []
        for link in links:
            stderr.write("Visiting {0}\n".format(link))
            stderr.flush()
            try:
                # Filter out invalid links
                if not link or "photobucket.com/" not in link:
                    continue

                # Modify the link when the page parameter is given, this is only the
                # case when album links were defined.
                if("page=" in link):
                    link = link[:link.rindex("page")]
                    link += "page="

                # Obtain the source code of the current link
                source = self._get_source(link)
                if not source:
                    stderr.write("\rFailed to obtain images from {0}!\n".format(link))
                    stderr.flush()
                    continue

                # Handle either albums or single image files, this check decides
                # which link is pointing to an album and which is not.
                if(self._is_album(source, link)):
                    # Since the current link is a link pointing to an album on Pb,
                    # we need to loop over each page and extract the images on it.
                    i = 1
                    status_counter = 0
                    while 1:
                        source = self._get_source(link + str(i))
                        if not source:
                            stderr.write("\nFailed to obtain images from {0}!\n".format(link))
                            stderr.flush()
                            break
                        elif "End of album" in source:
                            break
                        image_links = self._album(source)
                        if not image_links or image_links == "End of album":
                            break
                        else:
                            self._collected_links.extend(image_links)
                            self._collected_links = list(set(self._collected_links))
                            i += 1
                            status_counter += len(image_links)
                            stderr.write("\rCollected Links: {0}".format(status_counter))
                            stderr.flush()

                    stderr.write("\n")
                    stderr.flush()
                else:
                    # Here is the logic for single image links, pretty straight forward.
                    # extract the source (already done), filter the image info and store
                    # the info in an object.
                    image_link = self._single(source)
                    if not image_link:
                        stderr.write("\rFailed to obtain image from {0}!\n".format(link))
                        stderr.flush()
                        continue
                    self._collected_links.append(image_link)
            except(KeyboardInterrupt, EOFError):
                stderr.write("\n")
                stderr.flush()
                continue
        stderr.write("\n")
        stderr.flush()
        return self._collected_links

    def download_image(self, file_info):
        """ Downloads the image defined inside the passed fileinfo object. """
        if(file_info.media_type == "video" and not self._args.all_filetypes):
            return

        out = self._args.output_directory
        if not out:
            # Define the present working directory if it wasn't passed explicitly
            # with the -o/--output-directory argument.
            out = os.getcwd()
        elif out.startswith("~"):
            # Resolve the tilde char (which is the home directory on *nix) to
            # it's actual destination.
            home = os.environ.get("HOME")
            if not home:
                out = os.getcwd()
            else:
                out = out[1:]
                out = os.path.join(home, out)

        if not os.path.isdir(out) and not os.path.isfile(out):
            try:
                os.makedirs(out)
            except(OSError):
                stderr.write("Failed to create output directory, does it already exist?\n")
                stderr.flush()
                return

        # Add a trailing slash (or backslash) to the download directory, this is
        # necessary otherwise we would get an error when trying to write the down-
        # loaded file to the directory. (we want to write to file - not to the directory itself)
        if not out.endswith(os.sep):
            out += os.sep

        out = os.path.join(out, file_info.filename)
        # Handle duplicate file names
        unique = 1
        new_out = out
        while os.path.isfile(new_out):
            # Store the file extension and add a number between the name and the
            # extension, then rebuild the path and check if it exists, if it does
            # the whole process is repeated until an unique file name was built.
            file_extension = out[out.rindex("."):]
            new_out = out[:out.rindex(".")] + "(" + str(unique) + ")"
            new_out += file_extension
            unique += 1
            if(not os.path.isfile(new_out)):
                out = new_out

        # Fetch the url stored inside the fileinfo object and write the fetched
        # data into a file with the filename which is also stored inside the object.
        with open(out, "wb") as f:
            req = requests.get(file_info.link, stream=True)
            if req.status_code != requests.codes.ok:
                return
            for chunk in req.iter_content():
                if chunk:
                    f.write(chunk)
        self._downloaded_images += 1

    def download_all_images(self):
        """ Downlods all collected images. """
        for file_obj in self._collected_links:
            try:
                self.download_image(file_obj)
            except(KeyboardInterrupt, EOFError):
                break
            else:
                self._log_download_status()
        stderr.write("\n")
        stderr.flush()

    def _log_download_status(self):
        """ Prints the number of downloaded images and the total of images collected
            to stderr. """
        stderr.write("\rDownloaded images: {0}/{1}".format(self._downloaded_images,
                                                           len(self._collected_links)))
        stderr.flush()

    def _is_album(self, source, url):
        """ Identifies the url, returns true if the url is pointing to an album. """
        answer = False
        if("Links to share this album" in source or "page=" in url):
            answer = True
        return answer

    def _get_source(self, url):
        """ Returns the passed url's source code. """
        try: # Make the request with the passed url
            req = requests.get(url)
            if req.status_code != requests.codes.ok:
                raise requests.exceptions.RequestException
            elif(self._is_album("", url) and req.url != url):
                # The source of the passed url doesn't contain any signs whether
                # or not the page parameter actually points to a valid page,
                # it redirects to the first page when you try to visit page 6 when
                # the album has only 5 pages, thus we have to return a special
                # string which will be checked for after this function was called
                # to detect the end of the album. After the exception EOFError is
                # raised the string 'End of album' is returned.
                raise EOFError
        except(requests.exceptions.RequestException):
            return
        except(EOFError):
            return "End of album"
        else:
            source = req.text.encode("utf8", errors="ignore")
            return source

    def _single(self, source):
        """ Returns the image link from the passed source, None if not found. """
        # Try to find the json formated data blob which contains all info we need
        data = re.search("Pb\.Data\.Shared\.put\(Pb\.Data\.Shared\.MEDIA,.*?\);", source)
        if not data:
            return
        # Form the data to a valid json body
        data = data.group().replace("Pb.Data.Shared.put(Pb.Data.Shared.MEDIA,", "").strip()
        if(data.endswith(");")):
            data = data[:-2]
        try: # Parse the data blob
            j = json.loads(data)
        except(Exception):
            stderr.write("Exception occurred while parsing json data!\n")
            stderr.flush()
            return
        # Build the image info object and return it
        return ImageInfo(j["name"], j["title"], j["fullsizeUrl"], j["mediaType"],
                         j["likeCount"], j["commentCount"], j["viewCount"],
                         j["username"])

    def _album(self, source):
        """ Returns a list of image files from the passed source on success,
            None on failure. """
        # First we make sure the variable, which contains the album information
        # exists in the passed source, if not we abort.
        data = re.search("collectionData.*?\n", source)
        if not data:
            stderr.write("Failed to extract the data blob!\n")
            stderr.flush()
            return
        # Form the value of the variable in a valid json data blob
        data = data.group().replace("collectionData: ", "")
        data = data.strip()
        if(data.endswith("},")):
            data = data[:-1]

        image_objects = []
        try:
            # Parse the information and create "ImageInfo" objects
            j = json.loads(data)
            images = j["items"]["objects"]
            if not images:
                raise EOFError
            # Try to detect the first page and print the estimated file count
            # to stderr.
            if(j["pageNumber"] == 1):
                stderr.write("Estimated files in current album: {0}\n".format(j["total"]))
                stderr.flush()
        except(KeyError):
            stderr.write("KeyError occured!\n")
            stderr.flush()
            return
        except(EOFError):
            return "End of album"
        for obj in images:
            image_objects.append(ImageInfo(obj["name"], obj["title"],
                                           obj["fullsizeUrl"], obj["mediaType"],
                                           obj["likeCount"], obj["commentCount"],
                                           obj["viewCount"], obj["username"]))
        return image_objects




if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-f", "--file", help="A file containing one or more Photobucket"+\
                                            " links which you want to download.")
    group.add_argument("-u", "--url", help="A single url pointing to an album or image"+\
                                           " which is hosted on Photobucket.")
    parser.add_argument("-o", "--output-directory", help="The directory the extracted"+\
                                                         " images getting saved in.",
                        required=False)
    parser.add_argument("-a", "--all-filetypes",
                        help="Downloads all files regardless if it's a video or an image.",
                        action="store_true")
    args = parser.parse_args()

    pb = Photobucket(args)
    pb.extract()
    pb.download_all_images()

