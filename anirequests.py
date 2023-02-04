import requests
from requests_cache import CachedSession
import pandas as pd
import numpy as np
import json
import time

session = CachedSession('anilist_api', backend='sqlite',
                        expire_after=3600, allowable_methods=('GET', 'POST'))


def retrieve_data(nickname):
    '''
    Receives user nickname
    Returns user data from anilist API and response code
    '''
    query = '''
      query ($userName: String, $type: MediaType) {
    MediaListCollection(userName: $userName, type: $type) {
      lists {
        name
        isCustomList
        isCompletedList: isSplitCompletedList
        entries {
          ...mediaListEntry
        }
      }
      user {
        id
        name
        avatar {
          medium
        }
        statistics{
          anime{
            releaseYears {
              releaseYear
              count
              minutesWatched
              }
            genres{
              genre count
              }
            }
          }
        favourites {
          studios {
            nodes {
              id
              name
            }
          }
          staff {
            nodes {
              id
              name {
                full
              }
              image {
                medium
              }
            }
          }
          characters {
            nodes {
              id
              name {
                full
              }
              image {
                medium
              }
            }
          }
          anime {
            nodes {
              title {
                english
                romaji
                native
              }
              id
              coverImage {
                medium
              }
            }
          }
        }
        mediaListOptions {
          scoreFormat
          rowOrder
          animeList {
            sectionOrder
            customLists
            splitCompletedSectionByFormat
            theme
          }
          mangaList {
            sectionOrder
            customLists
            splitCompletedSectionByFormat
            theme
          }
        }
      }
    }
  }
  fragment mediaListEntry on MediaList {
    id
    mediaId
    status
    score
    progress
    repeat
    priority
    private
    hiddenFromStatusLists
    media {
      id
      duration
      title {
        english
        romaji
        native
      }
      coverImage {
        extraLarge
        large
      }
      type
      format
      status(version: 2)
      episodes
      genres
      bannerImage
    }
  }
  '''
    url = 'https://graphql.anilist.co'
    variables = {"userName": nickname, "type": "ANIME"}
    response = session.request(
        "POST", url, json={'query': query, 'variables': variables})
    now = time.ctime(int(time.time()))

    return response.json(), response.status_code


def get_data_from_json(json_content):
    '''
    Receives json content and unwraps neccessary data
    Returns user data dictionary and media list entry dataframe
    '''
    user = json_content['data']['MediaListCollection']['user']
    media_lists = json_content['data']['MediaListCollection']['lists']

    # User favourites data cleanup
    characters = user['favourites']['characters']['nodes']
    staff = user['favourites']['staff']['nodes']
    studios = user['favourites']['studios']['nodes']
    anime = user['favourites']['anime']['nodes']

    character_list = []
    for c in characters:
        id = c['id']
        name = c['name']['full']
        image = c['image']['medium']
        character_list.append({'id': id, 'name': name, 'image': image})

    staff_list = []
    for s in staff:
        id = s['id']
        name = s['name']['full']
        image = s['image']['medium']
        staff_list.append({'id': id, 'name': name, 'image': image})

    studio_list = []
    for s in studios:
        id = s['id']
        name = s['name']
        studio_list.append({'id': id, 'name': name})

    anime_list = []
    for a in anime:
        id = a['id']
        title_l = a['title'].values()
        for tl in title_l:
            if tl is not None:
                title = tl
                break
        image = a['coverImage']['medium']
        anime_list.append({'id': id, 'title': title, 'image': image})

    user['favourites']['characters'] = character_list
    user['favourites']['staff'] = staff_list
    user['favourites']['studios'] = studio_list
    user['favourites']['anime'] = anime_list

    # Processing list entries
    entries = []
    for list in media_lists:
        for el in list["entries"]:
            if el['private'] is not True:  # We skip private entries
                title_l = el['media']['title'].values()
                for tl in title_l:
                    if tl is not None:
                        title = tl
                        break
                mediaId = el['mediaId']
                genres = el['media']['genres']
                progress = el['progress']
                repeat = el['repeat']
                episodes = el['media']['episodes']
                type = el['media']['format']
                cover = el['media']['coverImage']['large']
                duration = el['media']['duration']
                score = el['score']
                status = el['status']
                entries.append([mediaId, title, genres, progress, repeat,
                               episodes, type, duration, score, status, cover])

    df = pd.DataFrame(entries, columns=['mediaId', 'title', 'genres', 'progress',
                      'repeat', 'episodes', 'type', 'duration', 'score', 'status', 'cover'])

    #Certain users have custom lists with overlapping entries - we have to remove them
    df.drop_duplicates(subset='mediaId', inplace=True)

    return df, user


def get_common_entries_list(frame1, frame2):
    '''
    Receives 2 dataframes or lists
    Returns list of common entries based on id
    '''
    # quick cheat to get dataframe from list
    if type(frame1) != 'pandas.core.frame.DataFrame' or type(frame2) != 'pandas.core.frame.DataFrame':
        frame1 = pd.DataFrame(frame1)
        frame2 = pd.DataFrame(frame2)
    if frame1.empty or frame2.empty:
        return None
    common = frame1.merge(frame2, how='inner',
                          on='id', suffixes=('', '_del'))
    common.drop(
        columns=[col for col in common if '_del' in col], inplace=True)

    return common.to_dict('records')


def calc_completion_stats(df1, df2, u1, u2):
    '''
    Receives user data dictionary and entries list
    Updates passed user data dictionary with completion statistics
    '''
    u1['total'] = df1.shape[0]
    u1['completed'] = df1[df1['status'] == "COMPLETED"].shape[0]
    u1['current'] = df1[df1['status'] == "CURRENT"].shape[0]
    u1['dropped'] = df1[df1['status'] == "DROPPED"].shape[0]
    u1['hold'] = df1[df1['status'] == "CURRENT"].shape[0]
    u1['planning'] = df1[df1['status'] == "PLANNING"].shape[0]

    u2['total'] = df2.shape[0]
    u2['completed'] = df2[df2['status'] == "COMPLETED"].shape[0]
    u2['current'] = df2[df2['status'] == "CURRENT"].shape[0]
    u2['dropped'] = df2[df2['status'] == "DROPPED"].shape[0]
    u2['hold'] = df2[df2['status'] == "CURRENT"].shape[0]
    u2['planning'] = df2[df2['status'] == "PLANNING"].shape[0]


def get_list_overlap(df1, df2):
    '''
    Receives user entries dataframes
    Returns overlap on completed and current status entries in 1-100 format
    '''
    df1_cw = df1[(df1['status'] == "COMPLETED") | (df1['status'] == "CURRENT")]
    df2_cw = df2[(df2['status'] == "COMPLETED") | (df2['status'] == "CURRENT")]
    common = df1_cw.merge(df2_cw, how='inner',
                          on='mediaId', suffixes=('_u1', '_u2'))
    min_length = min(df1_cw.shape[0], df2_cw.shape[0])
    matches = common.shape[0]
    return int(matches/min_length * 100)


def get_common_favourites(u1, u2):
    '''
    Receives user data dictionary
    Returns dictionary of common favourite anime,staff,studios and characters
    '''
    u1_anime = pd.DataFrame(u1['favourites']['anime'])
    u2_anime = pd.DataFrame(u2['favourites']['anime'])

    return {'anime': get_common_entries_list(u1['favourites']['anime'], u2['favourites']['anime']),
            'staff': get_common_entries_list(u1['favourites']['staff'], u2['favourites']['staff']),
            'studios': get_common_entries_list(u1['favourites']['studios'], u2['favourites']['studios']),
            'characters': get_common_entries_list(u1['favourites']['characters'], u2['favourites']['characters'])
            }


def get_time_spent(df1, df2):
    '''
    Receives user entries data frames
    Returns touple with 2 dataframes containing information about highest time spent on series
    '''
    # calculate time spent on each series
    df1.fillna(0, inplace=True)
    df2.fillna(0, inplace=True)
    df1['time_spent'] = df1['progress'] * df1['duration'] + \
        df1['repeat'] * df1['episodes'] * df1['duration']
    df2['time_spent'] = df2['progress'] * df2['duration'] + \
        df2['repeat'] * df2['episodes'] * df2['duration']
    df1.sort_values(by="time_spent", ascending=False, inplace=True)
    df2.sort_values(by="time_spent", ascending=False, inplace=True)
    u1_time_spent = df1[:5]
    u2_time_spent = df2[:5].sort_values(by="time_spent")

    # Drop unnecessary cols
    u1_time_spent = u1_time_spent.drop(
        columns=[col for col in u1_time_spent if col not in ["mediaId", "title", "time_spent", "cover"]])

    u2_time_spent = u2_time_spent.drop(
        columns=[col for col in u2_time_spent if col not in ["mediaId", "title", "time_spent", "cover"]])

    u1_time_spent.time_spent = u1_time_spent.time_spent.astype('int').apply(
        lambda x: '{:02d}h:{:02d}m'.format(*divmod(x, 60)))
    u2_time_spent.time_spent = u2_time_spent.time_spent.astype('int').apply(
        lambda x: '{:02d}h:{:02d}m'.format(*divmod(x, 60)))

    return u1_time_spent.to_dict('records'), u2_time_spent.to_dict('records')


def calc_genres_statistics(u1, u2):
    '''
    Receives user data dictionary
    Updates user data dictionary with sorted genres data
    '''
    # 7 highest entries per user
    genres = pd.DataFrame(u1['statistics']['anime']['genres'])
    genres.sort_values(by='count', inplace=True, ascending=False)
    genres = genres[:7]
    genres = genres.to_dict('records')
    u1['statistics']['anime']['genres'] = genres

    genres = pd.DataFrame(u2['statistics']['anime']['genres'])
    genres.sort_values(by='count', inplace=True, ascending=False)
    genres = genres[:7]
    genres = genres.to_dict('records')
    u2['statistics']['anime']['genres'] = genres


def get_release_year_data(u1, u2):
    '''
    Receives user data dictionary
    Return dictionary with labels representing years
    and data representing count of entries per year(ryc) or minutes watched per year(rym)
    '''
    # entries count and time watched by release year
    # ry-releaseYear c-count m-minutesWatched
    ry1 = pd.DataFrame(u1['statistics']['anime']['releaseYears'])
    ry2 = pd.DataFrame(u2['statistics']['anime']['releaseYears'])

    ry1.sort_values(by='count', inplace=True, ascending=False)
    ry2.sort_values(by='count', inplace=True, ascending=False)

    labels_c = set(ry1['releaseYear'][:5].to_list())
    labels_c.update(ry2['releaseYear'][:5].to_list())

    ry1.sort_values(by='minutesWatched', inplace=True, ascending=False)
    ry2.sort_values(by='minutesWatched', inplace=True, ascending=False)

    labels_m = set(ry1['releaseYear'][:5].to_list())
    labels_m.update(ry2['releaseYear'][:5].to_list())

    u1_ryc = ry1[ry1['releaseYear'].isin(labels_c)].drop(
        columns=['minutesWatched'])
    u2_ryc = ry2[ry2['releaseYear'].isin(labels_c)].drop(
        columns=['minutesWatched'])

    u1_rym = ry1[ry1['releaseYear'].isin(labels_m)].drop(columns=['count'])
    u2_rym = ry2[ry2['releaseYear'].isin(labels_m)].drop(columns=['count'])

    # handling missing values
    for label in labels_m:
        if label not in u1_rym['releaseYear'].tolist():
            new_row = pd.DataFrame(
                {'releaseYear': label, 'minutesWatched': 0}, index=[0])
            u1_rym = pd.concat([u1_rym, new_row], ignore_index=True)
        if label not in u2_rym['releaseYear'].tolist():
            new_row = pd.DataFrame(
                {'releaseYear': label, 'minutesWatched': 0}, index=[0])
            u2_rym = pd.concat([u2_rym, new_row], ignore_index=True)

    for label in labels_c:
        if label not in u1_ryc['releaseYear'].tolist():
            new_row = pd.DataFrame(
                {'releaseYear': label, 'count': 0}, index=[0])
            u1_ryc = pd.concat([u1_rym, new_row], ignore_index=True)
        if label not in u2_ryc['releaseYear'].tolist():
            new_row = pd.DataFrame(
                {'releaseYear': label, 'count': 0}, index=[0])
            u2_ryc = pd.concat([u1_ryc, new_row], ignore_index=True)

    u1_ryc.sort_values(by='releaseYear', inplace=True)
    u2_ryc.sort_values(by='releaseYear', inplace=True)
    u1_rym.sort_values(by='releaseYear', inplace=True)
    u2_rym.sort_values(by='releaseYear', inplace=True)

    rym = {'labels': sorted(labels_m), 'u1_data': u1_rym['minutesWatched'].tolist(
    ), 'u2_data': u2_rym['minutesWatched'].tolist()}
    ryc = {'labels': sorted(labels_c), 'u1_data': u1_ryc['count'].tolist(
    ), 'u2_data': u2_ryc['count'].tolist()}

    return ryc, rym


def get_entries_table(df1, df2, u1, u2):
    '''
    Receives user entries dataframes
    Returns html table comparing their entries
    '''
    # def wrap_img(link): -currently disabled due to putting a lot unnecessary load on anilist page
    #    '''
    #    Turns link into table img element
    #    '''
    #    return f'<img src="{link}" class="tableIMG"></img>'
    suff_1 = " " + u1['name']
    suff_2 = " " + u2['name']
    table_df = df1.merge(df2, on='mediaId', how='outer',
                         suffixes=[suff_1, suff_2])
    table_df['title'] = np.where(
        ~table_df['title'+suff_1].isnull(), table_df['title'+suff_1], table_df['title'+suff_2])
    #table_df['cover'] = np.where(~table_df['cover'+suff_1].isnull(),table_df['cover'+suff_1].apply(wrap_img), table_df['cover'+suff_2].apply(wrap_img))
    table_df = table_df[["title", "status" + suff_1,
                         "score" + suff_1, "status"+suff_2, "score"+suff_2]]
    table_df.loc[table_df["score" + suff_1] == 0, ("score" + suff_1)] = np.NaN
    table_df.loc[table_df["score" + suff_2] == 0, "score" + suff_2] = np.NaN
    html = table_df.to_html(na_rep="X", escape=False, index=False)

    lines = html.split("\n")
    lines[2] = '<tr>'
    lines[0] = '<table class="table table-dark table-hover"'
    lines.insert(1, 'data-toggle="table"')
    lines.insert(2, 'data-search="true"')
    lines.insert(3, 'data-show-columns="true"')
    lines.insert(4, 'data-pagination="true"')
    lines.insert(5, 'data-show-pagination-switch="true">')
    html = "\n".join(lines)

    return html

def get_data(df1, df2, u1, u2):
    '''
    Recieves user entries list dataframe and user information
    Returns creating dictionary with relevant user data
    '''
    calc_completion_stats(df1, df2, u1, u2)
    calc_genres_statistics(u1, u2)
    overlap = get_list_overlap(df1, df2)
    common_favs = get_common_favourites(u1, u2)
    u1_time_spent, u2_time_spent = get_time_spent(df1, df2)
    ryc, rym = get_release_year_data(u1, u2)
    table = get_entries_table(df1, df2, u1, u2)

    data = {'l1': u1_time_spent,
            'l2': u2_time_spent,
            'overlap': overlap,
            'u1': u1, 'u2': u2,
            'ryc': ryc, 'rym': rym,
            'common_favs': common_favs,
            'table': table}

    return data
