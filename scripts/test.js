// @ts-check

/** @type {number} */
const n = "not a number";

/** @type {{ foo: (x: number) => string }} */
const obj = {
	foo(x) {
		return x.toFixed(2);
	},
};

// Type errors:
obj.foo("bad");

// @ts-expect-error: intentional
n.toUpperCase();
