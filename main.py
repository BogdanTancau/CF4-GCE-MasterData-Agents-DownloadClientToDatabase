# 1 - imports
from decouple import config
import importlib
import traceback
import logging
from shutil import copy2
from sqlalchemy import text
import pandas as pd
import io
from google.cloud import storage
import chardet
import cloudstorage as gcs


Repository = importlib.import_module('services.repository')
Session = importlib.import_module('entities.base')
Company = importlib.import_module('entities.Company')
FetchSession = importlib.import_module('entities.fetch_base')

def run_agent(request):
    """Responds to any HTTP request.
    Args:
        request (flask.Request): HTTP request object.
    Returns:
        The response text or any set of values that can be turned into a
        Response object using
        `make_response <http://flask.pocoo.org/docs/1.0/api/#flask.Flask.make_response>`.
    """
    
    logging.info("Running Agent")
    print("Running Agent")
    
    # 2 - Get custom company
    request_json = request.get_json()
    request_args = request.args
    
    customCompany = None
    if request_json and 'company' in request_json:
        customCompany = request_json['company']
    elif request_args and 'company' in request_args:
        customCompany = request_args['company']

    logging.info(f"Custom Company: {0}", customCompany)
    print("Custom company: {0}".format(customCompany))
    
    # 3 - extract a session
    session = Session.Session()
    fetch_session = FetchSession.Session()

    # 4 - extract all companies
    try:
        logging.info("Beginning Processing Agent.")
        print("Beginning Processing Agent.")
        target = config("target")
        # companies = Repository.select(Company.Company, session, Company.Company.SNOWTarget, target)
        sql = text("select * from Companies WHERE SNOWTarget='prod' order by Name limit 15")
        result = session.execute(sql)
        companies = [row for row in result]
        logging.info(f"Retrieving companies: {0}", companies)
        print("Retrieving companies: {0}".format(companies))

        # # truncating all tables
        # tables = ["SNOWBuildingCache", "SNOWCompanyCache", "SNOWCostCenterCache", "SNOWDepartmentCache", "SNOWLocationCache", "SNOWUserCache"]
        # for table in tables:
        #     sql_query = ('TRUNCATE TABLE {0}'.format(table))
        #     session.execute(sql_query)
        #     logging.info(f"Truncating table: {0}".format(table))
        #     print("Truncating table: {0}".format(table))

        if customCompany is not None:
            companies = []
            # select data for specified custom company only
            companies = Repository.select2condition(Company.Company, session, Company.Company.SNOWTarget, target, Company.Company.Name, customCompany)
            companies = companies if isinstance(companies, list) else [companies]
            logging.info(f"Retrieving custom companies: {0}", companies)
            print("Retrieving custom companies: {0}".format(companies))
        
        # if there's no custom company specified, retrieve files for all companies from first query
        for company in companies:
            logging.info(f"Retrieving files for {0}", company.Name)
            print("Retrieving files for {0}".format(company.Name))

            # substracting beginning of the file path (bucket prefix)
            companyShortPath = 'clientData_utf16/{0}'.format(company.Ident)
            logging.info(f"Bucket prefix: {0}", companyShortPath)
            print("Bucket prefix: {0}".format(companyShortPath))

            # connecting to GCP storage
            storage_client = storage.Client()
            bucketName = config("Bucket")
            blobs = storage_client.list_blobs(bucketName, prefix=companyShortPath, delimiter=None)

            # listing files for given company
            for blob in blobs:
                logging.info(f"Reading file from bucket: {0}", blob.name)
                print("Reading file from bucket: {0}".format(blob.name))
                blobName = blob.name
                tableName = blobName.split("/")[2].split(".")[0]
                # substracting the name of destination table
                tableName = company.Ident + '_' + tableName.replace('_utf16','').replace(' ','')
                print(tableName)
                # tableNameCache = "SNOW{0}Cache".format(tableName.capitalize())
                logging.info(f"Destination table name: {0}", tableName)
                print("Destination table name: {0}".format(tableName))
                
            #     # handling name inconsistency between the database table and files from the bucket
            #     if tableNameCache == 'SNOWCostcenterCache': tableNameCache = 'SNOWCostCenterCache'

                extension = blobName.split(".")[1]
                print(extension)
                
                data = blob.download_as_string()

                ENCODING = 'utf-8'
                BOM = b''
                ENCODINGS = \
[
[ 'utf-32-be', b'\x00\x00\xFE\xFF' ],
[ 'utf-32-le', b'\xFF\xFE\x00\x00' ],
[ 'utf-16-be', b'\xFE\xFF' ],
[ 'utf-16-le', b'\xFF\xFE'  ],
[ 'utf-8-sig', b'\xEF\xBB\xBF' ]
]
                index = io.BytesIO(data).tell()
                mark = io.BytesIO(data).read(4)
                io.BytesIO(data).seek(index)
                for encoding in ENCODINGS:
                    if mark.startswith(encoding[1]):
                        ENCODING = encoding[0]
                        BOM = encoding[1]
                        break
                print(ENCODING, BOM)
                logging.info(ENCODING, BOM)
                # bucket = storage_client.bucket("gce-master-data")
                # blob_to_open = bucket.get_blob(blob.name)
                # with blob_to_open.open("rt") as f:
                #     print(f.read())
                # print("Encoding: {0}", charenc)
                # logging.info(f"Encoding: {0}", charenc)
                # reading files from the bucket into pandas dataframe
                if extension == 'csv':
                    data = blob.download_as_string()
                    # df = pd.read_csv('gs://' + blob.name, encoding='cp1252')
                    df = pd.read_csv(io.BytesIO(data))
                    logging.info(f'Pulled down file from bucket, file name: {0}', blob.name)
                    print('Pulled down file from bucket, file name: {0}'.format(blob.name))
                # if extension == 'txt':
                #     data = blob.download_as_string()
                #     df = pd.read_table(io.BytesIO(data))
                #     logging.info(f'Pulled down file from bucket, file name: {0}', blob.name)
                #     print('Pulled down file from bucket, file name: {0}'.format(blob.name))


                # loading files into specified table in the database
                    df.to_sql(name=tableName, con=fetch_session.get_bind(), if_exists = 'replace', index=False)
                    logging.info(f"File {0} uploaded to {1} table", blob.name, tableName)
                    print("File {0} uploaded to {1} table".format(blob.name, tableName))

    except Exception as e:
        logging.info(f"Exception not caught in Agent: {e}")
        print(f"Exception not caught in Agent: {e}")
        logging.error(traceback.format_exc())
        print(traceback.format_exc())
    
    return f'response: OK'

