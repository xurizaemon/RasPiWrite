#!/usr/bin/env python   

#  RasPiWrite - a Python script for writing Raspberry Pi distros to SD cards
#
#  Original code copyright (c) 2012 Matthew Jump
#  Modifications copyright (c) 2013 Patrick Knight
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.

import re, os, urllib2, time, sys, threading
from commands import *
from sys import exit
from random import choice
from xml.dom.minidom import parseString

# special text formatting
boldStart = '\033[1m'
end = '\033[0;0m'
WARNING = '\033[0;31m'

OS = os.uname() # gets OS vars

def grabRoot(distro): # parses the Raspberry Pi downloads page for the links to the current RasPiWrite-supported distros
  links = list()
  htmlSource = urllib2.urlopen('http://www.raspberrypi.org/downloads').read()
  linksList = re.findall('href="(.*)"',htmlSource)
  for link in linksList:
    if distro in link:
      if link.endswith('.zip') or link.endswith('.tar.bz2'):
        return link


def getZipUrl(url): # gets all the urls that end in .zip or .tar.bz2 (only two disk image archive types on the download web page)
  links = list()
  htmlSource = urllib2.urlopen(url).read()
  linksList = re.findall('<a href="?([^\s^"]+)',htmlSource)
  for link in linksList:
      if link.endswith('.zip') or link.endswith('.tar.bz2'):
         links.append(link)
  return links

def findDL(OS): # legacy reasons (Raspberry Pi website doesn't currently list Fedora - http://www.raspberrypi.org/phpBB3/viewtopic.php?f=2&t=5624)
  fedora = ['http://achtbaan.nikhef.nl/events/rpi/images/fedora/14/r1-06-03-2012/raspberrypi-fedora-remix-14-r1.img.gz',
      'http://mirror.star.net.uk/raspberrypi/images/fedora/14/r1-06-03-2012/raspberrypi-fedora-remix-14-r1.img.gz',
      'http://www.sqltuning.cz/raspberry/images/fedora/14/r1-06-03-2012/raspberrypi-fedora-remix-14-r1.img.gz',
      'http://raspberrypi.peir.com/images/fedora/14/r1-06-03-2012/raspberrypi-fedora-remix-14-r1.img.gz',
      'http://raspberrypi.mirror.triple-it.nl/images/fedora/14/r1-06-03-2012/raspberrypi-fedora-remix-14-r1.img.gz',
      'http://ftp.ticklers.org/RaspberryPi/images/fedora/14/r1-06-03-2012/raspberrypi-fedora-remix-14-r1.img.gz',
      'http://files.velocix.com/c1410/images/fedora/14/r1-06-03-2012/raspberrypi-fedora-remix-14-r1.img.gz',
      'http://raspberrypi.reon.hu/images/fedora/14/r1-06-03-2012/raspberrypi-fedora-remix-14-r1.img.gz']
  if OS == 'fedora': return choice(fedora)


def download(url): # downloads the disk image for the user (see http://stackoverflow.com/questions/22676)
  file_name = url.split('/')[-1]
  u = urllib2.urlopen(url)
  f = open(file_name, 'wb')
  meta = u.info()
  file_size = int(meta.getheaders('Content-Length')[0])
  print 'Downloading: %s Bytes: %s' % (file_name, file_size)
  file_size_dl = 0
  block_sz = 8192
  while True:
      buffer = u.read(block_sz)
      if not buffer:
          break
      file_size_dl += len(buffer)
      f.write(buffer)
      status = r'%10d  [%3.2f%%]' % (file_size_dl, file_size_dl * 100. / file_size)
      status = status + chr(8)*(len(status)+1)
      print status,
  f.close()

def cleanOutput(text2): # cleans up the output from df -h
  # ^(?=.*?\b/\b)(?=.*?\bdisk0)((?!Volume).)*$ <-- regex used
  # ^(?:.(?<!/Volumes))*$
  removeRootHDD = re.compile(r'(?=.*?\b/\b)(?=.*?\bdisk0)((?!Volume).)*')
  blacklist = re.compile(r'.*Backups|.*Backup.*|.*devfs.*|.*map.*')
  cleanOutput = re.sub(removeRootHDD, ' ', text2)
  filterblacklist = re.sub('(?m)^\s+', '', re.sub(blacklist,' ', cleanOutput))
  return filterblacklist

def matchSD(input): # grabs just the drive's name from the df -h command (only on OSX so far)
  selectSD = r'(?=/)(.*?)\s'
  match =  re.search(selectSD, input)
  if match is None:
    match = '0'
  return match

def unmount(location): # unmounts the drive so that it can be rewritten
  global OS
  print 'Unmounting the drive in preparation for writing...'
  if OS[0] != 'Darwin':
    output = getoutput('umount ' + location)
  else:
    output = getoutput('diskutil unmount ' + location)
  print output
  if 'Unmount failed for' in output:
    print WARNING + 'Error, the Following drive couldn\'t be unmounted, exiting...' + end
    exit()

class transferInBackground (threading.Thread):  # run the dd command in a seperate thread to give a waiting... indicator
  def run (self):
    global SDsnip
    global path
    if OS[0] != 'Darwin':
      copyString = 'dd bs=1M if=%s of=%s' % (path,SDsnip)
    else:
      copyString = 'dd bs=1m if=%s of=%s' % (path,SDsnip)
    print 'Running ' + copyString + '...'

    print getoutput(copyString)
    print 'done!'
     

def transfer(file,archiveType,obtain,SD,URL): #unzips the disk image
  global path
  if archiveType == 'zip': 
    path = file.replace('.zip', '') + '/' + os.path.basename(file).replace('.zip', '.img') # thanks Lewis Boon!
    extractCMD = 'unzip ' + file

  if archiveType == 'img': 
    path = file
    extractCMD = 'echo No extraction required for ' + file

  if archiveType == 'gz': 
    path = file.replace('.gz', '') # TODO: verify this works
    extractCMD = 'gunzip ' + file

  if archiveType == 'bz2':
    # QtonPi making me jump through hoops:
    basePath = file.replace('.tar.bz2', '')
    # this path is actually changed to something that the script can locate, such as the basepath
    extractPath = file.replace('.tar.bz2', '') + '/sdcard-img/' + re.search(r'(?=qtonpi)([^>]*)(?=-)', file).group(0) + '-sdcard' + re.search(r'(?=-)([^>]*)(?=.tar)', file).group(0) + '.img.bz2' # TODO: verify this works
    finalPath = file.replace('.tar.bz2', '') + '/sdcard-img/' + re.search(r'(?=qtonpi)([^>]*)(?=-)', file).group(0) + '-sdcard' + re.search(r'(?=-)([^>]*)(?=.tar)', file).group(0) + '.img'
    extractCMD = 'tar jxf ' + file
    path = basePath

  if obtain == 'dl': 
    obtainType = 'Downloaded by this client (reliable and safe)'
    if (os.path.exists(path)):
      print 'archive already has been extracted, skipping unzipping...'
      if archiveType == 'bz2':
        path = extractPath
        if (os.path.exists(path)):
          print 'Unzipping image..'
          print getoutput('bunzip2 ' + path)
        else:
          print 'Image has already been unzipped'
        path = finalPath
    else:
      download(URL)
      print 'Ok... Unzipping the disk , this may take a while...'
      print getoutput(extractCMD) # extract here!
      if archiveType == 'bz2':
        path = extractPath
        if (os.path.exists(path)):
          print 'Unzipping image..'
          print getoutput('bunzip2 ' + path)
        else:
          print 'Image has already been unzipped'
        path = finalPath
  if obtain == 'usr': 
    obtainType = 'Obtained by user and passed in (potentially dangerous)'
    print 'Found archive inputted by user, extracting...'
    if (os.path.exists(path)):
      print 'archive already has been extracted, skipping unzipping...'
      if archiveType == 'bz2':
        path = extractPath
        if (os.path.exists(path)):
          print 'Unzipping image..'
          print getoutput('bunzip2 ' + path)
        else:
          print 'Image has already been unzipped'
        path = finalPath

      if OS[0] != 'Darwin':
        print getoutput('pwd')
        path = getoutput('pwd')+ '/' + file.split('/')[-1].replace('.zip', '') + '/' + file.split('/')[-1].replace('.zip', '.img')
        print path
        print 'Not Darwin\n'
    else:
      print 'Ok... Unzipping the disk , this may take a while...'
      print getoutput(extractCMD) # extract here!
      if archiveType == 'bz2':
        path = extractPath
        if (os.path.exists(path)):
          print 'Unzipping image..'
          print getoutput('bunzip2 ' + path)
        else:
          print 'Image has already been unzipped'
        path = finalPath

      if OS[0] != 'Darwin':
        print getoutput('pwd')
        path = getoutput('pwd')+ '/' + file.split('/')[-1].replace('.zip', '') + '/' + file.split('/')[-1].replace('.zip', '.img')
        print path
        print 'Not Darwin\n'
  global SDsnip
  if (SD.find('/dev/mmcblk') + 1):
    SDsnip = '/dev/mmcblk' + SD[11]
  else:
    if OS[0] != 'Darwin': 
            SDsnip =  SD.replace(' ', '')[:-1]
    else:
      # remove weird partition notation in OSX partition names
            SDsnip =  SD.replace(' ', '')[:-2]

  print path
  print '\n\n###################################################################'
  print 'About to start the transfer procedure, here is your setup:'
  print '''
> OS Choice: %s
> SD Card: %s
> Type: %s
  ''' % (file.replace('.zip', ''), SDsnip, obtainType)
  print '''
Please remember that neither Matt Jump, exaviorn.com or any contributors can be held to warranty for any destruction of data or hardware 
(excerpt from GNU GPL, which can be found in the script's source, as well as inside the script's folder):
-----------------------------------------------------------------
This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
-----------------------------------------------------------------
  '''
  print '###################################################################\n'
  confirm = raw_input(boldStart + 'Please verify this information before typing \'accept\' to accept the terms and to start the process, if this information isn\'t correct, please press ctrl + c (^C), or type \'exit\' to quit: ' + end)
  if confirm == 'accept':
      thread1 = transferInBackground()
      thread1.start()
    sys.stdout.write('Waiting')
      sys.stdout.flush()
    while thread1.isAlive():
      time.sleep(3)
      sys.stdout.write('.')
        sys.stdout.flush()
      print 'Transfer Complete! Please remove the SD card'
      print '''###########################################
Relevent information:
> Debian - Login is pi/raspberry
> Arch - Login is root/root
> Fedora - Login is root/fedoraarm
> QtonPi - Login is root/rootme
###########################################
Thank You for using RasPiWrite, you are now free to eject your drive 
      '''
  else:
    print 'ENDING WITHOUT COPYING ANY DATA ACROSS, SD CARD HAS BEEN UNMOUNTED'
    exit()

def getImage(SD): # gives the user a bunch of options to download an image, or select their own, it then passes the user on to the transfer function
  global boldStart
  global end
  
  userChoice = raw_input('Do you wish to Download a Raspberry Pi compatible image (choose yes if you don\'t have one) (Y/n): ')
  
  if (userChoice == 'Y') or (userChoice == 'y'):
    print boldStart + '''
> Debian \'Squeeze\' [OPTION 1]''' + end + '''
Reference root filesystem from Gray and Dom, containing LXDE, Midori, development tools 
and example source code for multimedia functions.
    '''
    print boldStart + '''
> Arch Linux [OPTION 2]''' + end + '''
Arch Linux ARM is based on Arch Linux, which aims for simplicity and full control to the 
end user. Note that this distribution may not be suitable for beginners.
    '''
    print boldStart + '''
> Fedora 14 [OPTION 3]''' + end + '''
(raspberrypi-fedora-remix-14-r1)
The Raspberry Pi recommended choice for beginners, features a full GUI and applications for 
productivity and programming
    '''
    print boldStart + '''
> QtonPi [OPTION 4]''' + end + '''
QtonPi is an Embedded Linux platform plus SDK optimized for developing and running Qt 5 Apps on Raspberry Pi.
    '''
    osChoice = raw_input('Your Choice e.g: \'1\' : ')

    if osChoice == '1':
      URL = choice(getZipUrl(grabRoot('debian')))
      print 'Downloading Debian from [%s]'% URL
      match = grabRoot('debian').rpartition('/')
      transfer(match[-1],'zip','dl',SD,URL)
    if osChoice == '2':
      URL = choice(getZipUrl(grabRoot('arch')))
      print 'Downloading Arch Linux from [%s]'% URL
      match = grabRoot('arch').rpartition('/')
      transfer(match[-1],'zip','dl',SD,URL)
    if osChoice == '3':
      URL = findDL('fedora')
      print 'Downloading Fedora 14 from [%s]'% URL
      transfer('raspberrypi-fedora-remix-14-r1.img.gz','gz','dl',SD, URL)
    if osChoice == '4':
      URL = choice(getZipUrl(grabRoot('qtonpi')))
      print 'Downloading QtonPi 14 from [%s]'% URL
      match = grabRoot('qtonpi').rpartition('/')
      transfer(match[-1],'bz2','dl',SD, URL)

  if (userChoice == 'N') or (userChoice == 'n'):
    userLocate = raw_input('Please locate the disk image (.zip, .img.gz, .tar.bz2 (.tar.bz2 only working with QtonPi distros currently): ')
    if (os.path.exists(userLocate)):
      matchZip = re.match('^.*\.zip$',userLocate)
      matchGzip = re.match('^.*\.img.gz$',userLocate)
      matchBzip = re.match('^.*\.tar.bz2$',userLocate)
      matchImg = re.match('^.*\.img$',userLocate)

      if matchImg is not None:
        print 'Found Image file'
        transfer(userLocate,'img','usr',SD,'none')
      if matchZip is not None:
        print 'Found Zip'
        transfer(userLocate,'zip','usr',SD,'none')
      if matchGzip is not None:
        print 'found Gzip'
        transfer(userLocate, 'gz', 'usr',SD,'none')
      if matchBzip is not None:
        print 'found Bz2'
        transfer(userLocate, 'bz2', 'usr',SD,'none')  
        
    else:
      print 'sorry, the file you have specified doesn\'t exist, please try again'
      print 'Press ctrl + c (^C) to quit'
      exit()

def driveTest(SD):
    sdID = raw_input('I believe this is your SD card: ' + SD + ' is that correct? (Y/n) ')
    if (sdID == 'Y') or (sdID == 'y'): # continue
      unmount(SD)
      getImage(SD)
      
    if (sdID == 'N') or (sdID == 'n'):
      manualID = raw_input('Please enter the location you believe holds the SD Card: ')
      driveTest(manualID)

# program logic
# TODO: put this in a main() function at the least
print getoutput('clear')
print '//////////////////////// ' + boldStart + '''
RasPiWrite - a Python script for writing Raspberry Pi distros to SD cards ''' + end + '''
original script by Matt Jump, with modifications by Patrick Knight
////////////////////////
'''
if OS[0] != 'Darwin': # if not OSX, warn that it isn't completely supported
  print WARNING + 'WARNING: OSes other than Mac OS aren\'t fully supported, things may not work properly' + end
if not os.geteuid() == 0:
  print WARNING + 'Please run the script using sudo e.g. sudo python raspiwrite.py, or sudo ./raspiwrite.py (need to chmod +x first)' + end
  exit()
print 'The following script is designed to copy a Raspberry Pi compatible disk image to an SD Card'
print boldStart + 'INCORRECTLY FOLLOWING THE WIZARD COULD RESULT IN THE CORRUPTION OF YOUR HARD DISK, PARTITIONS OR A BACKUP USB DRIVE (INCLUDING MOUNTED TIME MACHINE BACKUP DRIVES)' + end
print 'It is advisable to remove any other USB HDDs or memory sticks, the wizard might select that one, %s if you have multiple hard drives installed, please take a LOT of care selecting the right drive %s' % (boldStart, end) 
text = getoutput('df -h')
raw_input('Now insert your SD Card, press enter when you are ready...')
text2 = getoutput('df -h')
print '''
\n---------------------------------------------------------
''' + boldStart + '''The following drives were found, please verify the name of the SD card in finder with the name under the \'Mounted On\' column (after \'/volumes/\'):
''' + end
volumes = cleanOutput(text2)
print volumes
print '---------------------------------------------------------\n'
if matchSD(volumes) == '0': #if no device found
  print WARNING + ''' 
  #############################################################
  WARNING: No reliable SD Card location could be found, please 
  insert a SD card device and try again, if you are certain 
  about the location of the SD card, you can manually override 
  it below
  #############################################################
  ''' + end
  manualID = raw_input('Please enter the location you believe holds the SD Card: ')
  driveTest(manualID)
else: # otherwise...
  SD = matchSD(volumes).group(1) # selects the first SD/USB drive located
  driveTest(SD) # action gets delegated to driveTest, which then leads on to the next step, I found this to be the easiest way