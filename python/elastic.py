#!/bin/env python

import sys,traceback
import os

import filecmp
import time
import shutil

import logging
import _inotify as inotify
import threading
import Queue

import elasticBand
import hltdconf
import collate

from anelastic import *



class BadIniFile(Exception):
    pass


class elasticCollector(LumiSectionRanger):
    
    def __init__(self, esDir):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.esDirName = esDir
    
    def process(self):
        self.logger.debug("RECEIVED FILE: %s " %(self.infile.basename))
        filepath = self.infile.infilepath
        fileType = self.infile.fileType
        eventType = self.eventType
        if eventType == "IN_CLOSE_WRITE":
            if self.esDirName in self.infile.path:
                if fileType in [INDEX,STREAM,OUTPUT]:   self.elasticize(filepath,fileType)
                if fileType in [EOR]: self.stop()
                self.infile.deleteFile()
                #self.infile.deleteFile()- DISABLED cause null jsn files
            elif fileType in [FAST,SLOW]:
                return
                #self.elasticize(filepath,fileType)


    def elasticize(self,filepath,fileType):
        self.logger.info(filepath)
        path = os.path.dirname(filepath)
        name = os.path.basename(filepath)
        if es and os.path.isfile(filepath):
            if fileType == FAST: es.elasticize_prc_istate(path,name)
            elif fileType == SLOW: es.elasticize_prc_sstate(path,name)             
            elif fileType == INDEX: 
                self.logger.info(name+" going into prc-in")
                es.elasticize_prc_in(path,name)
            elif fileType == STREAM:
                self.logger.info(name+" going into prc-out")
                es.elasticize_prc_out(path,name)
            elif fileType == OUTPUT:
                self.logger.info(name+" going into fu-out")
                es.elasticize_fu_out(path,name)

if __name__ == "__main__":
    logging.basicConfig(filename="/tmp/elastic.log",
                    level=logging.INFO,
                    format='%(levelname)s:%(asctime)s-%(name)s.%(funcName)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
    logger = logging.getLogger(os.path.basename(__file__))

    #STDOUT AND ERR REDIRECTIONS
    sys.stderr = stdErrorLog()
    sys.stdout = stdOutLog()


    #signal.signal(signal.SIGINT, signalHandler)
    
    eventQueue = Queue.Queue()

    conf=hltdconf.hltdConf('/etc/hltd.conf')
    dirname = sys.argv[1]
    dirname = os.path.basename(os.path.normpath(dirname))
    watchDir = os.path.join(conf.watch_directory,dirname)
    outputDir = conf.micromerge_output

    

    mask = inotify.IN_CLOSE_WRITE | inotify.IN_DELETE
    logger.info("starting elastic for "+dirname)
    mr = None
    try:
        #starting inotify thread
        mr = MonitorRanger()
        mr.setEventQueue(eventQueue)
        mr.register_inotify_path(watchDir,mask)
        mr.start_inotify()

        es = elasticBand.elasticBand('http://localhost:9200',dirname)
        os.makedirs(os.path.join(watchDir,ES_DIR_NAME))

        #starting elasticCollector thread
        ec = elasticCollector(ES_DIR_NAME)
        ec.setSource(eventQueue)
        ec.start()

    except Exception as e:
        logger.exception("error")
        logger.error("when processing files from directory "+dirname)

    logging.info("Closing notifier")
    if mr is not None:
      mr.stop_inotify()

    logging.info("Quit")
    sys.exit(0)
