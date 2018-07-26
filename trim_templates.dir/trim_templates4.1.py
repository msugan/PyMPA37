#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
import numpy as np
import glob
from obspy import read
from obspy import read_inventory, read_events, Stream, Trace
from obspy.core.utcdatetime import UTCDateTime
from obspy.geodetics import gps2dist_azimuth
from obspy.taup.taup_create import build_taup_model
from obspy.taup.tau import TauPyModel


def kilometer2degrees(kilometer, radius=6371):
    """
    Convenience function to convert kilometers to degrees assuming a perfectly
    spherical Earth.

    :type kilometer: float
    :param kilometer: Distance in kilometers
    :type radius: int, optional
    :param radius: Radius of the Earth used for the calculation.
    :rtype: float
    :return: Distance in degrees as a floating point number.

    """
    pi = 3.14159265359
    return kilometer / (2.0 * radius * pi / 360.0)


def read_input_par(trimfile):

    with open(trimfile) as tf:
        data = tf.read().splitlines()

    stations = data[16].split(" ")
    channels = data[17].split(" ")
    networks = data[18].split(" ")
    lowpassf = float(data[19])
    highpassf = float(data[20])
    tlen_bef = float(data[21])
    tlen_aft = float(data[22])
    UTC_prec = int(data[23])
    cont_dir = "./" + data[24] + "/"
    temp_dir = "./" + data[25] + "/"
    day_list = str(data[26])
    ev_catalog = str(data[27])
    start_itemp = int(data[28])
    stop_itemp = int(data[29])
    taup_model = str(data[30])
    invfiles = data[16].split(" ")
    return stations, channels, networks, lowpassf, highpassf, tlen_bef,\
        tlen_aft, UTC_prec, cont_dir, temp_dir, day_list, ev_catalog, \
        start_itemp, stop_itemp, taup_model, invfiles


def read_sta_inv(invfile, sta):
    inv = read_inventory(invfile)
    nt0 = inv.select(station=sta)
    lat = nt0[0].station[0].latitude
    lon = nt0[0].station[0].longitude
    elev = nt0[0].station[0].elevation
    return lat, lon, elev


trimfile = './trim.par'

# lat, lon, elev = read_sta_inv(invfile, station)
# print(lat, lon, elev)

[stations, channels, networks, lowpassf, highpassf, tlen_bef, tlen_aft,
 UTC_prec, cont_dir, temp_dir, day_list, ev_catalog, start_itemp, stop_itemp,
 taup_model] = read_input_par(trimfile)

# -------
# Define our bandpass min and max values
bandpass = [lowpassf, highpassf]

# Duration to use for template before and after s-waves arrival time in seconds
tmplt_dur = tlen_bef

# ---Read the Catalog of template in zmap_format, filtered by day---#
cat = read_events(ev_catalog, format="ZMAP")
ncat = len(cat)

# ---- The following lines are needed because the input zmap has no decimal year
# ---- in the corresponding column, but fractions of seconds are in the seconds field
aa = np.loadtxt(ev_catalog)
aa1 = aa[:, 9]
aa2 = aa1 - np.floor(aa1)
aa3 = aa2 * 1000000

st = Stream()
st1 = Stream()
st2 = Stream()
fname = "%s" % day_list

# array of days is built deleting last line character (/newline) ls -1 command
# include a newline character at the end
with open(fname) as fl:
    days = [line[:-1] for line in fl]
    print(days)

fl.close()
tvel = "./" + taup_model + ".tvel"
build_taup_model(tvel)

for ista in stations:

    for day in days:
        print("day == ", day)
        inpfiles = cont_dir + day + "." + ista + ".???"
        st.clear()

        for file in glob.glob(inpfiles):
            st += read(file)

        st.merge(method=1, fill_value=0)
        st.detrend('constant')
        st.filter('bandpass', freqmin=bandpass[0],
                  freqmax=bandpass[1], zerophase=True)
        dataYY = int("20" + day[0:2])
        dataMM = int(day[2:4])
        dataDD = int(day[4:6])

        # to avoid errors in the input trim.par at stop_itemp
        if stop_itemp > ncat:
            stop_itemp = ncat

        for iev in range(start_itemp, stop_itemp):
            ot = cat[iev].origins[0].time.datetime
            ot1 = UTCDateTime(ot)
            yy = ot1.year
            mm = ot1.month
            dd = ot1.day
            hh = ot1.hour
            minu = ot1.minute
            sec = ot1.second
            microsec = aa3[iev]
            m = cat[iev].magnitudes[0].mag
            lon = cat[iev].origins[0].longitude
            lat = cat[iev].origins[0].latitude
            dep = cat[iev].origins[0].depth
            # depth in km
            dep = dep / 1000
            microseci = int(microsec)
            ot0 = UTCDateTime(yy, mm, dd, hh, minu, sec, microseci)
            ot2 = UTCDateTime(yy, mm, dd)
            ot3 = UTCDateTime(dataYY, dataMM, dataDD)

            if ot2 == ot3:
                eve_coord = [lat, lon, dep]

            print("ista", ista)

            for invfile in invfiles:
                try:
                    slat, slon, selev = read_sta_inv(invfile, ista)
                    print(ista, slat, slon, selev)
                except:
                    pass

            print("Station not found in inventories")
            eve_lat = eve_coord[0]
            eve_lon = eve_coord[1]
            eve_dep = eve_coord[2]

            if eve_dep < 1.5:
                eve_dep = 1.5

            epi_dist, az, baz = gps2dist_azimuth(eve_lat, eve_lon, slat, slon)
            epi_dist = epi_dist / 1000
            print("epi_dist==", epi_dist)
            deg = kilometer2degrees(epi_dist)
            print("deg==", deg)
            print("eve_dep==", eve_dep)
            model = TauPyModel(model=taup_model)
            arrivals = model.get_travel_times(source_depth_in_km=eve_dep,
                                              distance_in_degree=deg,
                                              phase_list=["s", "S"])
            arrS = arrivals[0]
            print("arrS.time=...", arrS.time)

            stime = UTCDateTime(ot0) + arrS.time - tlen_bef
            print("stime", stime)
            etime = UTCDateTime(ot0) + arrS.time + tlen_aft
            print("etime", etime)

            # cut the 3-component template and save file
            nchannels = len(channels)

            for ichan in range(0, nchannels):
                print("ista", ista)
                st1.clear()
                # print("FILE", file)
                st1 = st.copy()
                tw = Trace()
                st2.clear()
                print(st1.select(station=ista, channel=channels[ichan]))
                st2 = st1.select(station=ista, channel=channels[ichan])

                if st2.__nonzero__():
                    tw = st2[0]

                    if tw.trim(stime, etime).__nonzero__():
                        print(tw)
                        netwk = tw.stats.network
                        ch = tw.stats.channel
                        tw.trim(stime, etime)
                        newfile = temp_dir + str(iev) + "." + netwk +\
                            "." + ista + ".." + ch + ".mseed"
                        print(newfile)
                        tw.write(newfile, format="MSEED")
                    else:
                        pass

                else:
                    pass
