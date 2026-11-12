"""Subset 2 of the reviewed ASAI flow specifications."""
from __future__ import annotations

import ast
import base64
import zlib

FLOW_SPECS_PART_2: dict[str, tuple[str, tuple[str, ...]]] = ast.literal_eval(
    zlib.decompress(base64.b85decode('c-qBVU9aP|5&bKD+b&Su1l_0hZId==fCkxa0`yU!B+6n;kqSxqUT@L=-ZMi|l6|i~WP8z<tgkF{hBIeo&J3CVyc?wR$_Hs`S*S+#gQd^=Z^YQBP;~gpx_x1+>xEWdL{Qee`|BV6c<OiW{)F#>^r75~UYEV>@$;vTwAfGl`B!}BpZJZmgfH{zvMG1;%o==3qRVF$Iy;6^OW}+%8%VfT04*R(C)?3WUyjC$R+fzjq7<engXp2bENR8UY@BKN-(-zVRH7-zP?tgVcm->-kU_Yhgf6w+ynFv163*MZRT_^?kQ=AM{!xaG>Slu~U)D~FfSnIc?eKv$&HG4Z>TM%eSfp3p!#S@-LE*68w0VK7l;8JSnQc;3G}6I+TR7Esf?TL=y}i+YMgnssBgDw?Y~A*}qnz|WV%<%#kswRZyvkpBffB#K-}vd%=k(~u{A8hPHboKx=XF9EwnQ@yTGiyh#@1sm4J;)lNXlli$V!pfna6Hqp#)KSlCX2DjO^JQAV>f$(tupVB}p^ZIJp_Ma8sDB^A4%&_jt4aD&Bbupx6>zkssY|ATb9eP!5n|wKvk$%5|TSS>(Ber;OW=0r?&{P~l!L8~h=UEyKpjSo5+T0bQV~S3&KhpF|GUhYjSGF)xY(p`X&1KhEDR#3Sn>RIsM0)c}ww(@AXKm)7Wg89GG2jqk8kTv>}jR7z9sT?aD}Y_IC8bM{Iz`p&w^b5?7rHucTOs_bYQc%!y38r(r{;9U56!EF0i_FgO}U*I|tQMN*9a^kFFO4wm^NL*Z3q;uBYCP?&^+KhHY3bZ{?!t(HkwjR65s3qYn+Bz(cJsKeJ5nyUZQ}Z@CWf7nPuS1cl%ishGXM7>6aN9N!5xod?hdmKjsf4F+t)&{mv1Ju;Cm5#Q8vCqevq8?kfZN|k$XGrr9MKgQt^=+ZhNq9ia1i1{BokY?Fa79t6uf0xl(obc_}V(E+N$v=R;+c6y{HArxUh7i+E#M<NSi1dY1E>~4Qh}`D`YIPC>P78PwC<3>DglaX@|6Ch=q=l5ei(?R@BaVf}25dO0wg=pqdu@ha@RC0-_PC4%XR$2~(AQ2^31RiaI7{QpN*pia0XhFxwArTBzTnSR$C8{)Rt)$$!1I>3W}c5!0a;y+i^;#RaF(K>1!<F~`+RHbh+`gHUBS54J|uiY!hK@p{-7l`_rMJZTVkB{_mqmH?moL=S(aXWykqi>+mWCCTw+6x%8Yigg*CfL5Chp-hR=QC(PMhSlOg#IQ_L${k6n*?0tOC&4C5k#Tx~_jBPWa$si3U&}<4GE?dYco^Cq%n`PVbc@MwY!47|exO9OtcrJ7YYrktT8`pQfL*>Ia{_{B{3a)^#r0zS8LCN$C)TR5d@b)-)=Ql%Cf!a_$SY3wWVl-R?r3RxDXq&NKQ=_+g#+7tGaGGW$OwwaLQ&4m8JB*dQShCQzl8DCCN%=JcWs2(L`<kg(6Zme@`%4(F;!|t*Q-}&T;(TE|6qDU`QW?sXla^Qc(F3<xG~5XWaX4iM3|ZqNw|6mr5$8cS6dK1dTX-SbpnmWPwiH8M2(Zkh}yh5Lb~SeggZP@Ez;w&(AyF%#xpVAy!WS{+m_11zwzY{@w=R~4+7oUNE9hCdVni%sR)o362+lPMe<^j_VM%J>`of7gxwu#$d^HI{zP*tkmNuNxZd^L33rxAc4;lOX0lOCMPlOXC28s(p+lf7<fuH1ZbR|aTPpWjR8l80vO|jD-3xl1at=&GwTvbskI=zOFfb-xknJ>h1KA`Je$s<$utOaMQ$j~Cfs5Aa#-EH3l;;9=Dq1OvMR9vfkXTATl+=3easdwJ+sGxHG@$H`a>Ak#UAJ&IQih;qp!S0E5Hj-sfJNo>%#Z~IKV^n&wPGWNf?0@oT&~EAm-E6?bC|pc;`<^Q3s%Q|0$o4$2zBD%VPq6>)>&yQlqK{FWDr^murfr{&_xVdrVNWR)Ft}HdeSp`d9WxYbE2{lpv=7Rj?jBl=nUJ>c=$0rTjDiR%0;@25zCWEWkiD_CBViI-<o>JQx2jOuFNoog1UBT9)?kZAdyb|7uB*vLAGrik?sfR-N}0ES6UpT7M@JbmN5-AGKiXt%!7qw3eYnO&3o*dakLmAL2qoL({(J5Ie+gTk$zr_n;TPZ%D|}F7LFv&!2UXuc}%M|1@U=w2Kz$wWST^^9^%?#KV;KK$*J{^(vMwnod8PeUx>FI91)ahCt6N@O`PT}`=iG=<MrNJXTL~uAUJM!Oma^$B?TUin%#`Gg6ai~cgYJ=XOACG{oeOl9nd6IN(v^+|8RPqg-oS^ry~(R(!DWoJ1yWu&dMyZQ8WVbH_lw@S`Hzm<xw-9JnyJg&S&lu?My`(OhY<8$ob7L9DGYuH?&l*48W&q{w3#ZJvQ8#2q-H1JigL2HDu@BmrADg7klvK7wIf5<H5`cVtlkiKt1#zx?=?SIaFmPyrQgL;rE<~=5}W^Gzc<$7G)q2L3?x_1#06)p2cRJ)*x+4eQ9V5OTb?9%z)0nxO&_Mwp@o2*3xt<jqrGc6z7!9ZOfZc>(otA140N*m4XgUE{VFWGUbgR$&NMgmwBKPyD`p@kcK1-V5by(21?{kCaXE>9|$DWW7wjNgK(|!j~@qMi%Q(vUOk`nsQXql6wAzJnVptrj#CCp6XeJ6fkYUIWmK}Ivp!+=(;|<lK52t9WjYcb8>4d$<#d01Om(k6=U385hq_~^nU6R#(w9~EhWY6nuTdUwoE6TajEcM9-cnGZ0;aj@h!Al3I>8MIXnBIvSQ!&V^2V9Wc2$<JKw&yUm_s$;cN+8Bfwq5}gv!}1jlzBMjiQ!1C7obLn*86kFu9w?Y1l%}(2Y|hBJb#~xS9??l8hO%XmOCdWZRN+9uZhQimT=U*q(A{qg6GjoVqpAU_N?Ehzk2R(KL<I!BmFPFTwRg{N{W9Vo7{rf6k<12Y<y=p2=)^@r;lhS8!pR)twA^F_64s9t{=5{4VqTm4|#u4xx-Q%n_erqM14Rtp|yL=5C|Yvycj=n0H2ecd*KYyKf}Sms29a$?%TlyGB{1Q9n(5xNXgpCpv+vODk&Wi(a^`3<Y)G-?TJtD3p9DvYPCIx8I)q5Fc{${`64~q89(8?j!stU;Z^B%>h%;WuZG?Euph!o^qEgw(LR}U^MwM+bAAUyc!s;mN%WbQyT^WEe(y+tsdmf$|frfB6L1iMn1lzG;}z`{+%Rv9%8ewPtXsc?hdDtF*gcUjxP?yJ-2C|12W1Z;hHsN+46;8NDd@dt(KX?d3pB=k%vu!uf$xMcX||{t3^$SqiromYk6Tb2jh95v6P~wJ4y)qe7x~hu*O27n%U}+&k_C*a|0b-<OBKJAvRF>IvV@}tJc#g`y%QVNAY7k@4H#hV)@B(^l2CGI+={?77BF+1SQG@1$Z`B_+<Lo*YU<etIS)1&~iD=j0n6x*e5F1)*n86_)ByKr{mbcdp=tO0W(y-T9<ArG-{*5`uNiz74f};0ZiOo+F8~pUh<(#;O*$BD5T@kEBr$(+HuePa4)@Xqqh>QLm;(*I_+bhXe)ZD)Oe)t@mA^=7__`_ZqxbXDi5pDTpE0f?jOK(Y>o@(i@zZB<$*NBpo|m9qvNW1tE|H!t=)Nsd6US?IGCzaJRko`;hOJ7<vbZn=%2s+Hj;|0!_=hai!54-E!|&3TD>EZ=k@t;UL?C6OfGp)!Sncqr`8h^r-@I`0;dkDwOZTfl8z4@$Ha7g6f4S&nS#o5tj80{q1Wd7VqA~N+H$TPM7Q58+N(i1Lys>RqDd$_zC#@MXZdC=%`7Y1?Bg-bLXCJ!!S~~4qnEYpHeEc~cX9N@A}9M-T)t8BP_7-Fbr0Nz9$X|j5h!993a!w9?Q1OyKK{NcN?zZ(;#n#O0SySi(WYh7z3Ia_Vw!NAzQt9IAR!g3oK~KWKk+*lBR-6saJulq_XyTzJL&+b38?uDz#B36&W3bl`DHG)cRDbyMFhSa(OJ?S22BP|d@ElnneM!C!y0;SlTeK*mQQPu`q7_2H~(&$UoHLT;8L)jRA5S)co<z3K^2KLnJqjiafLB2ZTf24UP35e$gGuCoX(03C8`@?x}_UEbP!O{g{GNURU#fq%wo=9vlj;7o~Kply=WfGS&N3-%l{$Z%(gP6IlR8Leoxa)vJ;#nHzU(D`Ct&%s@9&_>*6L;?8M^SJ6=Fr8*NCSI&}R10gM$?j8t=2%zT60O0#xZnsP12##9B5?>Vhpa*n|m9Jw*<N6*tqA%<9%_|k3ehvU0++X&6weZf;%8|aL6NJ-8~5C&oww423<alQhVZ+Kl}!b{Ts@7sS2QZ7lk1~~8E|M!2p?3t$'.encode("ascii"))).decode("utf-8")
)

# Reviewed paper connection and private deployment cases, assigned explicitly.
_PAPER_AND_DEPLOY_CASES = {
    "interfaces-market-data/quote-json-validation": (
        "test_demo_paper_connection.PaperConnectionTests.test_rejects_malformed_and_untrusted_json",
    ),
    "interfaces-market-data/quote-transport-bounds": (
        "test_demo_paper_connection.PaperConnectionTests.test_content_length_truncation_rejected",
        "test_demo_paper_connection_worker.PaperConnectionTests.test_deadline_terminates_a_stalled_local_worker_without_output",
        "test_demo_paper_connection.PaperConnectionTests.test_real_chunked_response_truncation_and_body_limit",
        "test_demo_paper_connection.PaperConnectionTests.test_real_detached_http_responses_are_closed_on_every_path",
        "test_demo_paper_connection.PaperConnectionTests.test_response_cleanup_errors_do_not_prevent_connection_cleanup",
        "test_demo_paper_connection.PaperConnectionTests.test_response_body_size_boundary",
        "test_demo_paper_connection_worker.PaperConnectionTests.test_isolated_python_worker_runs_with_mocked_transport",
        "test_demo_paper_connection_worker.PaperConnectionTests.test_worker_deadline_and_private_ipc",
    ),
    "interfaces-market-data/app-lifecycle-audit": (
        "test_demo_private_deploy.PrivateDeployTests.test_configuration_is_fixed_and_help_explains_limits",
        "test_demo_private_deploy_lifecycle.PrivateDeployTests.test_preflight_and_simulator_integration_no_secret_logs",
    ),
}
for _flow, _cases in _PAPER_AND_DEPLOY_CASES.items():
    _category, _existing = FLOW_SPECS_PART_2[_flow]
    FLOW_SPECS_PART_2[_flow] = (_category, _existing + _cases)
del _flow, _cases, _category, _existing, _PAPER_AND_DEPLOY_CASES
