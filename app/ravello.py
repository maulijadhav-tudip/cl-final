from app import flaskapp
from bson import json_util
import json
import time
import datetime
import requests
import dateutil.parser
import logging

HEADERS = {
    'cache-control': "no-cache",
    'Content-Type': 'application/json',
    'Accept': 'application/json'
}

VERIFY  =  not flaskapp.config['DEBUG']
BASE_URL = "https://cloud.ravellosystems.com/api/v1/"
# BASE_URL = "http://localhost:8000/"
def buckets():
    url = BASE_URL + "costBuckets"
    return requests.request(
        "GET", url, headers=HEADERS, auth=(flaskapp.config['RAVELLO_EMAIL'], flaskapp.config['RAVELLO_PASSWORD']), verify=VERIFY).text


def locations(id):
    url = BASE_URL + "blueprints/" + \
        str(id) + "/publishLocations"
    return requests.request(
        "GET", url, headers=HEADERS, auth=(flaskapp.config['RAVELLO_EMAIL'], flaskapp.config['RAVELLO_PASSWORD']), verify=VERIFY).text


def blueprints():
    url = BASE_URL + "blueprints"
    return requests.request(
        "GET", url, headers=HEADERS, auth=(flaskapp.config['RAVELLO_EMAIL'], flaskapp.config['RAVELLO_PASSWORD']), verify=VERIFY).text


def delete_env(env):
    url = BASE_URL + "applications/" + str(env)
    response = requests.request(
        "DELETE", url, headers=HEADERS, auth=(flaskapp.config['RAVELLO_EMAIL'], flaskapp.config['RAVELLO_PASSWORD']), verify=VERIFY)
    flaskapp.logger.info("Env " + str(env) + " deleted.")
    return response.status_code


def delete_token(tokenID):
    url = BASE_URL + "ephemeralAccessTokens/" + \
        str(tokenID)
    response = requests.request(
        "DELETE", url, headers=HEADERS, auth=(flaskapp.config['RAVELLO_EMAIL'], flaskapp.config['RAVELLO_PASSWORD']), verify=VERIFY)
    flaskapp.logger.info("Token " + str(tokenID) + " deleted.")
    return response.status_code


def set_env_expiration(env, duration):
    url = BASE_URL + "applications/" + \
        str(env) + "/setExpiration"
    data = {
        "expirationFromNowSeconds": int(duration) * 60
    }

    response = requests.request(
        "POST", url, headers=HEADERS, auth=(flaskapp.config['RAVELLO_EMAIL'], flaskapp.config['RAVELLO_PASSWORD']), json=data, verify=VERIFY)
    flaskapp.logger.info("Env " + str(env) + " expiration updated.")
    return response.status_code


def update_application_name(env, name, blueprint):
    settings = flaskapp.config['SETTINGS_COLLECTION'].find_one()
    url = BASE_URL + "applications/" + str(env)
    raw = requests.request(
        "GET", url, headers=HEADERS, auth=(flaskapp.config['RAVELLO_EMAIL'], flaskapp.config['RAVELLO_PASSWORD']), verify=VERIFY).text
    json_dict = json.loads(raw)
    json_dict['name'] = name
    response = requests.request(
        "PUT", url, headers=HEADERS, auth=(flaskapp.config['RAVELLO_EMAIL'], flaskapp.config['RAVELLO_PASSWORD']), json=json_dict, verify=VERIFY)

    flaskapp.logger.info("Env " + str(env) + " name updated.")
    return response.status_code


def update_token(tokenName, tokenID, duration, env):
    url = BASE_URL + "ephemeralAccessTokens/" + \
        str(tokenID)
    raw = requests.request(
        "GET", url, headers=HEADERS, auth=(flaskapp.config['RAVELLO_EMAIL'], flaskapp.config['RAVELLO_PASSWORD']),  verify=VERIFY).text
    json_dict = json.loads(raw)
    json_dict['expirationTime'] = int(
        round(time.time() * 1000)) + (int(duration) * 60 * 1000)
    json_dict['name'] = tokenName
    response = requests.request(
        "PUT", url, headers=HEADERS, auth=(flaskapp.config['RAVELLO_EMAIL'], flaskapp.config['RAVELLO_PASSWORD']), json=json_dict, verify=VERIFY)
    flaskapp.logger.info("Token " + str(tokenName) + " updated.")
    return response.status_code


def create_or_assign_env(name, lab, classId=None):
    if classId:
        hot = flaskapp.config['CLASS_COLLECTION'].find_one_and_update({"id": classId},{'$pop': {'envs': -1 },  '$inc': {"usedEnvs": 1}})
    else:
        hot = flaskapp.config['HOT_COLLECTION'].find_one_and_update({"lab._id": lab['_id'], "startTime": {"$lt":datetime.datetime.utcnow() + datetime.timedelta(minutes=15)}, "endTime":{"$gt":datetime.datetime.utcnow()}},{'$pop': {'envs': -1 },  '$inc': {"usedEnvs": 1}})
    if hot and len(hot['envs']) > 0:
        return hot['envs'][0]
    else:
        return create_env(name, int(lab['blueprint']['id']))


def create_env(name, blueprint):

    settings = flaskapp.config['SETTINGS_COLLECTION'].find_one()

    url = BASE_URL + "applications"
    data = {
        "name": name,
        "baseBlueprintId": blueprint,
        "costBucket": {"id": settings['bucket']['id']}
    }
    response = requests.request(
        "POST", url, headers=HEADERS, auth=(flaskapp.config['RAVELLO_EMAIL'], flaskapp.config['RAVELLO_PASSWORD']), json=data, verify=VERIFY)

    failCount = 0

    try:
        # If the API Call Fails, Keep Trying
        while response.status_code != 201:
            # If failed a certain amount, send an email to the admin
            if failCount == int(flaskapp.config['API_FAIL']):
                raise Exception(
                    "Creating Application has failed " + str(failCount) + " times.")

            response = requests.request(
                "POST", url, headers=HEADERS, auth=(flaskapp.config['RAVELLO_EMAIL'], flaskapp.config['RAVELLO_PASSWORD']), json=data, verify=VERIFY)
            flaskapp.logger.error("Error Creating Application " + name + ", trying again, Response: " +
                                     str(response.status_code))
            failCount += 1
            time.sleep(18)

    except:
        flaskapp.logger.critical("Error Creating Application " + name + ", Response: " +
                                 str(response.status_code) + ", Skipping user")
        return 1

    if response.status_code == 201:
        response_data = json.loads(response.text)
        flaskapp.logger.info("Created Env " + str(response_data['id']))
        return response_data['id']

    return 1


def publish_env(env, lab, duration):
        # API Call to publish app
    url = BASE_URL + "applications/" + \
        str(env) + "/publish"

    if lab['optimizationLevel'] == "PERFORMANCE_OPTIMIZED":
        data = {
            "optimizationLevel": "PERFORMANCE_OPTIMIZED",
            "preferredRegion": lab['region']
        }
    else:
        data = {
            "optimizationLevel": "COST_OPTIMIZED"
        }

    response = requests.request(
        "POST", url, headers=HEADERS, auth=(flaskapp.config['RAVELLO_EMAIL'], flaskapp.config['RAVELLO_PASSWORD']), json=data, verify=VERIFY)

    failCount = 0

    try:
        # If API Call fails, retry
        while response.status_code != 202:
                # If failed a certain amount, send an email to the admin
            if failCount == int(flaskapp.config['API_FAIL']):
                raise Exception(
                    "Creating Application has failed " + str(failCount) + " times.")

            response = requests.request(
                "POST", url, headers=HEADERS, auth=(flaskapp.config['RAVELLO_EMAIL'], flaskapp.config['RAVELLO_PASSWORD']), json=data, verify=VERIFY)
            flaskapp.logger.error("Error Publishing Application, trying again, Response: " +
                                     str(response.status_code))
            failCount += 1
            time.sleep(18)
    except:
        flaskapp.logger.critical("Error Publishing Application " + str(env) + ", Response: " +
                                 str(response.status_code) + ", Skipping user")
        return 1

    url = BASE_URL + "applications/" + \
        str(env) + "/setExpiration"
    data = {
        "expirationFromNowSeconds": int(duration) * 60
    }
    response = requests.request(
        "POST", url, headers=HEADERS, auth=(flaskapp.config['RAVELLO_EMAIL'], flaskapp.config['RAVELLO_PASSWORD']), json=data, verify=VERIFY)

    if response.status_code != 200:
        return 1

    flaskapp.logger.info("Published Env " + str(env))
    return 0


def create_token(name, duration, env):
    url = BASE_URL + "ephemeralAccessTokens"
    data = {
        "name": name,
        "expirationTime": int(round(time.time() * 1000)) + (int(duration) * 60 * 1000),
        "permissions": [
            {
                "actions": [
                    "READ",
                    "EXECUTE"
                ],
                "resourceType":  "APPLICATION",
                "filterCriterion": {
                    "type":  "COMPLEX",
                    "operator":  "And",
                    "criteria": [
                        {
                            "type":  "SIMPLE",
                            "operator":  "Equals",
                            "propertyName":  "ID",
                            "operand":  env
                        }
                    ]
                }
            }
        ]
    }
    response = requests.request(
        "POST", url, headers=HEADERS, auth=(flaskapp.config['RAVELLO_EMAIL'], flaskapp.config['RAVELLO_PASSWORD']), json=data, verify=VERIFY)

    failCount = 0

    try:
        while response.status_code != 201:
            if failCount == int(flaskapp.config['API_FAIL']):
                raise Exception("Creating Token has failed " +
                                str(failCount) + " times.")
            response = requests.request(
                "POST", url, headers=HEADERS, auth=(RAVELLO_EMAIL, RAVELLO_PASSWORD), json=data, verify=VERIFY)
            flaskapp.logger.error("Error Creating token, trying again" +
                                     str(response.status_code))
            time.sleep(18)
    except:
        flaskapp.logger.critical("Error Creating Token Application " + name + ", Response: " +
                                 str(response.status_code) + ", Skipping user")
        return 1

    if response.status_code == 201:
        response_data = json.loads(response.text)
        flaskapp.logger.info("Created Token " + str(response_data['token']))
        data['token'] = response_data['token']
        data['tokenID'] = response_data['id']
        return data
    return 1


def delete_app_by_email(email):
    user = flaskapp.config['USERS_COLLECTION'].find_one(
        {"email": email})
    if user:
        if user['createdApp']:
            delete_env(str(user['env']))

        if user['createdToken']:
            delete_token(str(user['tokenID']))


def create_or_assign_env_to_user(user):
    if not user['createdApp']:
        result = create_or_assign_env(
            user['email'] + "-" + user['lab']['blueprint']["name"], user['lab'])
        if isinstance(result, int):
            if result != 1:
                flaskapp.config['USERS_COLLECTION'].update_one({
                    'email': user['email']
                }, {
                    '$set': {
                        'createdApp':  True,
                        'env': result
                    }
                })
            else:
                return 1
        else:
            set_env_expiration(result['env'], user['duration'])
            update_token(user['email'] + "-" + user['lab']['blueprint']
                         ["name"], result['tokenID'], user['duration'], result['env'])
            update_application_name(
                result['env'], user['email'] + "-" + user['lab']['blueprint']["name"], user['lab']['blueprint']['id'])

            flaskapp.config['USERS_COLLECTION'].update_one({
                'email': user['email']
            }, {
                '$set': {
                    'createdApp':  True,
                    'env': result['env'],
                    'tokenID': result['tokenID'],
                    'token': result['token'],
                    'publishedTime': result['publishedTime'],
                    'createdToken': True,
                    'startTime': datetime.datetime.utcnow(),
                    'endTime': datetime.datetime.utcnow() + datetime.timedelta(minutes=int(user['duration']))
                }
            })
    return 0


def publish_or_assign_env_to_user(user,enteredClass):
    if not user['createdApp']:
        result = create_or_assign_env(
            user['email'] + "-" + user['lab']['blueprint']["name"], user['lab'], enteredClass['id'])
        if isinstance(result, int):
            if result != 1:
                flaskapp.config['USERS_COLLECTION'].update_one({
                    'email': user['email']
                }, {
                    '$set': {
                        'createdApp':  True,
                        'env': result
                    }
                })

                user = flaskapp.config['USERS_COLLECTION'].find_one(
                    {"email": user['email']})

                result = publish_env(
                    user['env'], user['lab'], user['duration'])
                if result != 1:

                    if user['startTime'] == "":
                        user['startTime'] = datetime.datetime.utcnow()
                        user['endTime'] = datetime.datetime.utcnow(
                        ) + datetime.timedelta(minutes=int(user['duration']))

                    result1 = create_token(
                        user['email'] + "-" + user['lab']['blueprint']["name"], user['duration'], user['env'])

                    if result1 != 1:
                        user['token'] = result1['token']
                        user['tokenID'] = result1['tokenID']
                        user['publishedTime'] = datetime.datetime.utcnow()
                        user['createdToken'] = True
                        flaskapp.config['USERS_COLLECTION'].update_one({
                            'email': user['email']
                        }, {
                            '$set': user
                        })


                    else:
                        return 1
                else:
                    return 1
            else:
                return 0
        else:
            set_env_expiration(result['env'], user['duration'])
            update_token(user['email'] + "-" + user['lab']['blueprint']
                         ["name"], result['tokenID'], user['duration'], result['env'])
            update_application_name(
                result['env'], user['email'] + "-" + user['lab']['blueprint']["name"], user['lab']['blueprint']['id'])

            flaskapp.config['USERS_COLLECTION'].update_one({
                'email': user['email']
            }, {
                '$set': {
                    'createdApp':  True,
                    'env': result['env'],
                    'tokenID': result['tokenID'],
                    'token': result['token'],
                    'publishedTime': result['publishedTime'],
                    'createdToken': True,
                    'startTime': datetime.datetime.utcnow()
                }
            })
    return 0
