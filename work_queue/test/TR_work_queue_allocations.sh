#!/bin/sh
set -ex

. ../../dttools/test/test_runner_common.sh

python=${CCTOOLS_PYTHON_TEST_EXEC}
python_dir=${CCTOOLS_PYTHON_TEST_DIR}

STATUS_FILE=wq.status
PORT_FILE=wq.port

check_needed()
{
	[ -n "${python}" ] || return 1
}

prepare()
{
	rm -f $STATUS_FILE
	rm -f $PORT_FILE

	return 0
}

run()
{
	# worker resources (used by worker in factory in wq_alloc_test.py):
	cores=4
	memory=200
	disk=200
	gpus=8

	echo $(pwd) ${python}

	# send makeflow to the background, saving its exit status.
	export PATH=/bin:/usr/bin
	export PATH=$(pwd)/../src:$(pwd)/../../batch_job/src:$PATH
	export PYTHONPATH=$(pwd)/../src/bindings/${python_dir}
	${python} wq_alloc_test.py $PORT_FILE $cores $memory $disk $gpus; echo $? > $STATUS_FILE

	# retrieve wq script exit status
	status=$(cat $STATUS_FILE)
	if [ $status -ne 0 ]
	then
		exit 1
	fi

	exit 0
}

clean()
{
	rm -f $STATUS_FILE
	rm -f $PORT_FILE

	rm -rf input.file
	rm -rf output.file
	rm -rf executable.file
	rm -rf testdir

	exit 0
}


dispatch "$@"

# vim: set noexpandtab tabstop=4:
