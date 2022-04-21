import pandas as pd
import numpy as np
import re
import json
import argparse
import tldextract
import sys
from pandas.io.json import json_normalize
from urllib.parse import urlparse
from core.graph import *

def parseUrlRoot(urlvalue):
        try:
            cleanurl = urlparse(urlvalue)#.netloc
            cleanurl = cleanurl.hostname
            return str(cleanurl)
        except:
            # If urlparse due to weird characters like "[", utilize generic url to avoid downstream issues.
            # TODO: I'm sure there is probably a better way to handle this.
            urlvalue = "https://icicles.io"
            cleanurl = urlparse(urlvalue)#.netloc
            cleanurl = cleanurl.hostname
            return str(cleanurl)

def parseUrlBase(urlvalue):
    # Normalize URLs to avoid duplicate urls if it is http or https and has standard ports. Was discovering duplicate urls with and without port.
    try:
        baseurl = urlparse(urlvalue)
        if (baseurl.port == 443 or baseurl.port == 80):
            baseurl = baseurl.scheme + '://' + baseurl.hostname + baseurl.path
        else:
            baseurl = baseurl.scheme + '://' + baseurl.netloc + baseurl.path
        return str(baseurl)
    except:
        # If urlparse due to weird characters like "[", utilize generic url to avoid downstream issues.
        # TODO: I'm sure there is probably a better way to handle this.
        urlvalue = "https://icicles.io"
        baseurl = urlparse(urlvalue)
        baseurl = baseurl.scheme + '://' + baseurl.hostname + baseurl.path
        return str(baseurl)

def processEnrichURLs(programScope, dfAllURLs): # dataframe requires domain column
    
    programName = programScope['program']
    
    ScopeInURLs, ScopeInGithub, ScopeInWild, ScopeInGeneral, ScopeInIP, ScopeOutURLs, ScopeOutGithub, ScopeOutWild, ScopeOutGeneral, ScopeOutIP = extrapolateScope(programScope['program'],programScope['in_scope'],programScope['out_of_scope'])

    dfAllURLs['domain'] = dfAllURLs['url'].apply(parseUrlRoot)
    dfAllURLs['baseurl'] = dfAllURLs['url'].apply(parseUrlBase)
    dfAllURLs['program'] = programName
    
    # Scope mapper
    mapperIn = {True: 'in', False: 'other'}  # in = within the defined scope
    mapperOut = {True: 'out', False: 'in'} # out = explicitly out of scope
    mapperWild = {True: 'wild', False: 'out'} # wild - within the wildcard scope
     # other = not in scope but not explicitly excluded
    
    # This checks to determine whether a url is explicitly defined as out-of-scope
    dfAllURLs['scopeOut'] = dfAllURLs.domain.str.lower().isin([x.lower() for x in ScopeOutGeneral]).map(mapperOut)
    # This checks to determine whether a url is explicitly defined as in-scope
    dfAllURLs['scopeIn'] = dfAllURLs.domain.str.lower().isin([x.lower() for x in ScopeInGeneral]).map(mapperIn)
    
    # This section checks for wildcard scopes and determines whether a url is included within the wildcard scope
    lstWild = []
    for wild in ScopeInWild:
        wild = re.sub(r'^.*?\*\.', '', wild)
        lstWild.append(wild.lower())
        #print(wild)
    
    dfAllURLs['scopeWild'] = dfAllURLs.domain.str.lower().str.endswith(tuple(lstWild)).map(mapperWild)
    
    # This section creates a normalized scope field to track in, out, wild, or other
    conditions = [
        (dfAllURLs['scopeOut'] == 'out'),
        (dfAllURLs['scopeIn'] == 'in') & (dfAllURLs['scopeOut'] != 'out'),
        (dfAllURLs['scopeWild'] == 'wild') & (dfAllURLs['scopeIn'] != 'in') & (dfAllURLs['scopeOut'] != 'out'),
        (dfAllURLs['scopeIn'] == 'other') & (dfAllURLs['scopeWild'] != 'wild') & (dfAllURLs['scopeIn'] != 'in') & (dfAllURLs['scopeOut'] != 'out')
    ]
    
    # Each of these values maps to the equivalent condition listed
    values = ['out', 'in', 'wild', 'other']                                                                           
    
    # Create a new column and assign the values specific to the conditions.
    # TODO - This could potentially miss items since it is a select. Need to perform some searches on whether or not scope column is populated after using this for a while.
    dfAllURLs['scope'] = np.select(conditions, values)
    return dfAllURLs

def boundaryGuard(dfAllURLs, urlOutputPath, programScope):
    
    programName = programScope['program']

    dfAllURLs = processEnrichURLs(programScope, dfAllURLs)

    # File path that does not contain explicitly out-of-scope items
    storeModPathUrl = urlOutputPath + programName + '-urls-mod.txt'
    # File path that only contains explicitly in-scope urls
    storeInPathUrl = urlOutputPath + programName + '-urls-in-full.txt'
    # File path that only contains explicitly in-scope urls
    storeBasePathUrl = urlOutputPath + programName + '-urls-in-base.txt'
    storeOutPathUrl = urlOutputPath + programName + '-urls-out.txt'
    detailedURLOutput = urlOutputPath + programName + '-details.csv'

    # Output URLs that are in-scope
    dfURLsIn = dfAllURLs[(dfAllURLs['scope'] == 'in') | (dfAllURLs['scope'] == 'wild')]
    dfURLsIn['url'].drop_duplicates().to_csv(storeInPathUrl, header=None, index=False, sep='\n')
    # This only outputs the base URL so that it can be used for fuzzing
    dfURLsIn['baseurl'].drop_duplicates().to_csv(storeBasePathUrl, header=None, index=False, sep='\n')
    
    # Output URLs that are not explicitly out-of-scope
    dfURLsMod = dfAllURLs[dfAllURLs['scope'] != 'out']
    dfURLsMod['url'].drop_duplicates().to_csv(storeModPathUrl, header=None, index=False, sep='\n')
    
    # Output URLs that are explicitly out-of-scope
    dfURLsOut = dfAllURLs[dfAllURLs['scope'] == 'out']
    dfURLsOut['url'].drop_duplicates().to_csv(storeOutPathUrl, header=None, index=False, sep='\n')
    
    dfAllURLs.to_csv(detailedURLOutput, columns=['url','domain','baseurl','program','scope'], index=False)
    
    # Output metrics within log
    print('Total number of urls: ' + str(len(dfAllURLs['url'].drop_duplicates())))
    print('Number of urls not explicitly out-of-scope: ' + str(len(dfURLsMod['url'].drop_duplicates())))
    print('Number of urls explicitly in-scope: ' + str(len(dfURLsIn['url'].drop_duplicates())))
    print('Number of urls out-of-scope: ' + str(len(dfURLsOut['url'].drop_duplicates())))
    print('Number of unique domains: ' + str(len(dfAllURLs['domain'].drop_duplicates())))
    
    dfURLsIn['url'].drop_duplicates().to_csv(sys.stdout, header=None, index=False, sep='\n')
    
    generateGraph(outputDir,dfAllURLs,programName)
    
    return dfAllURLs

def processSingleDomain(domainName):
    domainList = []
    ext = tldextract.extract(domainName)
    if (ext.suffix is not ''):
        rootDomain = ext.domain + '.' + ext.suffix
        domainList.append(rootDomain)
        if (ext.subdomain is not ''):
            subDomain = ext.subdomain
            subs = subDomain.split('.')
            subLength = len(subs) - 1
            while subLength >= 0:
                rootDomain = subs[subLength] + '.' + rootDomain
                domainList.append(rootDomain)
                subLength = subLength - 1
    else:
        rootDomain = ext.domain
        domainList.append(rootDomain)
        subDomain = ext.subdomain
        subs = subDomain.split('.')
        subLength = len(subs) - 1
        while subLength >= 0:
            rootDomain = subs[subLength] + '.' + rootDomain
            domainList.append(rootDomain)
            subLength = subLength - 1
    return domainList

def processBulkDomains(dfAmass):
    listDomains = []
    try:
        listDomains = dfAmass['subdomain'].unique().tolist()
    except:
        print('No subdomain column')
    try:
        listDomains += dfAmass['domain'].unique().tolist()
    except:
        print('No domain column')
    tempDomains = []
    for val in listDomains: 
        tempDomains = processSingleDomain(val)
        listDomains = listDomains + tempDomains
    setDomains = set(listDomains)
    return setDomains

def cleanupScopeGithub(dfIn):
    matchString = 'github.com'
    matches = []
    for match in dfIn:
        match = re.search("(?P<url>https?://[^\s]+)", match)
        if match is None:
            continue
        else:
            match = match.group('url')
            if matchString in match:
                matches.append(match)
            else:
                continue
    return matches
def cleanupScopeStrict(dfIn):
    matchString = 'github.com'
    matches = []
    for match in dfIn:
        #if matchString in match:
        match = re.search("(?P<url>https?://[^\s]+)", match)
        if match is None:
            continue
        else:
            match = match.group('url')
            if matchString in match:
                continue
            else:
                matches.append(match)
    return matches

def cleanupScopeWild(dfIn):
    matchString = '\*.'
    matches = []
    for match in dfIn:
        match = re.search("(?P<url>[*][^\s|\,]+)", match)
   
        if match is None:
            continue
        else:
            match = match.group('url')
            matches.append(match)
    return matches

def cleanupScopeIP(dfIn):
    matchString = '\*.'
    matches = []
    for match in dfIn:
        
        match = re.search("(?P<url>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?:/\d{1,2}|))", match)
        
        if match is None:
            continue
        else:
            match = match.group('url')
            matches.append(match)
    return matches

def cleanupScopeGeneral(dfIn):
    matchStringSpace = ' '
    matchStringGit = 'github.com'
    matchStringUrl = 'http'
    matchStringWild = '\*.'
    matchStringDot = '.'
    matches = []
    for match in dfIn:
        matchWild = re.search("(?P<url>[*][^\s|\,]+)", match)
        matchDot = re.search("(?P<url>[.][^\s]+)", match)
        matchIP = re.search("(?P<url>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?:/\d{1,2}|))", match)
        if matchStringGit in match:
            continue
        elif matchStringSpace in match:
            continue
        elif matchStringUrl in match:
            url = urlparse(match)
            match = url.netloc
            matches.append(match)
            continue
        elif matchIP is not None:
            continue
        elif matchWild is not None:
            match = match.replace('*.','')
            matches.append(match)
            continue
        elif matchDot is None:
            continue
        else:
            matches.append(match)
    return matches

def extrapolateScope(programName, listscopein, listscopeout):
    ScopeInURLs = cleanupScopeStrict(listscopein)
    ScopeInGithub = cleanupScopeGithub(listscopein)
    ScopeInWild = cleanupScopeWild(listscopein)
    ScopeInGeneral = cleanupScopeGeneral(listscopein)
    ScopeInIP = cleanupScopeIP(listscopein)
    ScopeOutURLs = cleanupScopeStrict(listscopeout)
    ScopeOutGithub = cleanupScopeGithub(listscopeout)
    ScopeOutWild = cleanupScopeWild(listscopeout)
    ScopeOutGeneral = cleanupScopeGeneral(listscopeout)
    ScopeOutIP = cleanupScopeIP(listscopeout)
    return ScopeInURLs, ScopeInGithub, ScopeInWild, ScopeInGeneral, ScopeInIP, ScopeOutURLs, ScopeOutGithub, ScopeOutWild, ScopeOutGeneral, ScopeOutIP

def loadScope(scopeFile):
    programData = open(scopeFile)
    programScope = json.load(programData)
    return programScope